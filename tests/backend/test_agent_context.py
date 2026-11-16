"""Prompt/context assembly: full history, untruncated catalog, stable budget errors."""
import json
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.agent import context
from app.core.database import write_transaction
from app.models import PublicExercise, Message
from helpers import call, content, reply, send, setup


def message_count(engine, cid):
    with Session(engine) as db:
        return db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id == cid))


def test_long_history_is_sent_in_full_and_ordered(env):
    _, (a, _) = env
    rounds = {'n': 0}
    def model(messages, tools):
        rounds['n'] += 1
        return reply('第%d轮回复' % rounds['n'])
    cid, _ = setup(a, model)
    for _ in range(30):
        send(a, cid, '第%d句' % rounds['n'])
        # keep the model replying with plain text forever
        a.app.state.ai_provider.fn = model
    seen = {}
    def inspect(messages, tools):
        roles = [m['role'] for m in messages]
        seen['messages'] = messages
        seen['user_texts'] = [m['content'] for m in messages if m['role'] == 'user']
        return reply('结束')
    a.app.state.ai_provider.fn = inspect
    send(a, cid, '最后一句')
    assert message_count(a.app.state.engine, cid) == 62  # 31 user + 31 assistant
    texts = seen['user_texts']
    # context JSON message + every user turn, in order
    assert len(texts) == 32
    assert texts[1] == '第0句' and texts[-2] == '第29句' and texts[-1] == '最后一句'
    assert seen['messages'][0]['role'] == 'system'
    assert '以下 JSON 为当前业务上下文' in seen['messages'][1]['content']


def test_catalog_is_never_truncated(env):
    engine, (a, _) = env
    with write_transaction(engine) as db:
        for index in range(400):
            db.add(PublicExercise( name='批量动作%d' % index))
    seen = {}
    def inspect(messages, tools):
        seen['context'] = messages[1]['content']
        return reply('好')
    cid, _ = setup(a, inspect)
    send(a, cid, '看看目录')
    parsed = json.loads(seen['context'].split('\n\n', 1)[1])
    assert len(parsed['catalog']) >= 400
    assert all(item['name'] for item in parsed['catalog'])


def test_read_only_mode_only_offers_query_tools_and_notes_mode(env):
    _, (a, _) = env
    seen = {}
    def inspect(messages, tools):
        seen['tools'] = [t['name'] for t in tools]
        seen['context'] = messages[1]['content']
        seen['system'] = messages[0]['content']
        return reply('只能查询')
    cid, _ = setup(a, inspect)
    send(a, cid, '查询一下', mode='read')
    assert seen['tools'] == ['get_profile', 'get_training_plan_context', 'list_operations', 'list_workouts', 'get_workout']
    assert '只读模式' in seen['system']
    assert '"mode": "read"' in seen['context']


def test_pending_action_is_exposed_in_context(env):
    engine, (a, _) = env
    from sqlalchemy import select
    from app.core.database import write_transaction
    from app.models import ConversationAction, Turn, User
    cid, _ = setup(a, lambda messages, tools: reply('好'))
    with write_transaction(engine) as db:
        user_id = db.scalars(select(User.id)).first()
        turn = Turn(user_id=user_id, conversation_id=cid, token='x', deadline=0, context={'mode': 'edit'})
        db.add(turn)
        db.flush()
        db.add(ConversationAction(user_id=user_id, conversation_id=cid, turn_id=turn.id,
                                  operation='create_workout', tool_name='save_workout',
                                  tool_contract_version='1', payload={}, summary='待确认的训练内容', details={}))
    with Session(engine) as db:
        from app.agent.tools import build_registry
        messages = context.fresh_messages(db, user_id, cid, 'edit',
                                          build_registry().schemas(), read_only=False)
    parsed = json.loads(messages[1]['content'].split('\n\n', 1)[1])
    assert parsed['pending_action']['operation'] == 'create_workout'
    assert parsed['pending_action']['summary'] == '待确认的训练内容'


def test_over_budget_context_fails_with_stable_error(env, monkeypatch):
    engine, (a, _) = env
    monkeypatch.setattr(context.provider_module, 'context_limit', lambda: 100)
    cid, model = setup(a, lambda messages, tools: reply('不该被调用'))
    result = send(a, cid, '你好')
    assert result['status'] == 'failed'
    assert result['error'] == 'context_too_large'
    assert model.calls == []  # the model was never called
    # History is preserved, nothing truncated.
    assert message_count(engine, cid) == 1


def test_current_date_context_uses_user_timezone(env, monkeypatch):
    from app.models import User

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz):
            return datetime(2026, 1, 2, 1, tzinfo=timezone.utc).astimezone(tz)

    monkeypatch.setattr(context, 'datetime', FixedDatetime)
    engine, (client, _) = env
    with write_transaction(engine) as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.profile = {**(user.profile or {}), 'timezone': 'America/Los_Angeles'}

    def inspect(messages, tools):
        runtime = json.loads(messages[1]['content'].split('\n\n', 1)[1])
        assert runtime['today'] == '2026-01-01'
        assert runtime['timezone'] == 'America/Los_Angeles'
        assert 'selected_date' not in runtime
        assert '未指定训练日期时使用 today' in messages[0]['content']
        assert '选中日期' not in messages[0]['content']
        return reply('好')

    cid, _ = setup(client, inspect)
    assert send(client, cid)['status'] == 'succeeded'


def test_tool_date_schema_only_describes_field_contract():
    from app.agent.tools.workouts import ToolContent

    field = ToolContent.model_json_schema()['properties']['actual_date']
    assert field['format'] == 'date'
    assert field['description'] == '训练实际发生日期，格式 YYYY-MM-DD'
    assert 'actual_date' in ToolContent.model_json_schema()['required']
