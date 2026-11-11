"""Prompt/context assembly: full history, untruncated catalog, stable budget errors."""
import json

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.agent import context
from app.core.database import write_transaction
from app.models import Exercise, Message
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
    assert '以下 JSON 是当前轮次的业务上下文' in seen['messages'][1]['content']


def test_catalog_is_never_truncated(env):
    engine, (a, _) = env
    with write_transaction(engine) as db:
        for index in range(400):
            db.add(Exercise(owner_id=None, name='批量动作%d' % index))
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
    assert seen['tools'] == ['list_workouts', 'get_workout']
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
        messages = context.fresh_messages(db, user_id, cid, 'edit', None,
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
