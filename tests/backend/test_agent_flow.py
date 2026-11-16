"""Agent loop: bounded rounds, SSE results, retry traces and proposal lifecycle."""
import json
import asyncio
import time
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.agent.contracts import ModelReply, ToolCallRequest
from app.agent.provider import ProviderError
from helpers import FakeProvider, call, content, make_workout, reply, send, setup, write


def tool_call(id, name, **arguments):
    return ModelReply(type='tool_calls', calls=[ToolCallRequest(id=id, name=name, arguments=arguments)])


def messages_of(a, cid):
    return a.get('/api/conversations/' + cid).json()['messages']


def test_over_budget_batch_is_entirely_rejected(env, monkeypatch):
    from app.agent import runner
    from app.agent.tools import workouts
    _, (a, _) = env
    monkeypatch.setitem(runner.LIMITS, 'tool_calls', 3)
    queried = []
    real_query = workouts.query_workouts
    def query(*args, **kwargs):
        queried.append(True)
        return real_query(*args, **kwargs)
    monkeypatch.setattr(workouts, 'query_workouts', query)
    rounds = []
    def model(messages, tools):
        rounds.append(True)
        return ModelReply(type='tool_calls', calls=[
            ToolCallRequest(id=f'{len(rounds)}-{i}', name='list_workouts', arguments={'on': '2026-01-02'}) for i in range(2)])
    cid, _ = setup(a, model)
    result = send(a, cid)
    assert result['error'] == 'agent_loop_limit'
    assert len(queried) == 2  # second batch has only one slot left, neither runs
    results = [json.loads(m['content']) for m in messages_of(a, cid) if m['role'] == 'tool']
    assert len(results) == 4
    assert all(r['error']['code'] == 'tool_call_limit' for r in results[-2:])


def test_total_timeout_cancels_model_without_creating_card(env, monkeypatch):
    from app.agent import runner
    from app.models import ConversationAction
    engine, (a, _) = env
    monkeypatch.setitem(runner.LIMITS, 'total_seconds', 0.05)
    async def slow(messages, tools):
        await asyncio.sleep(1)
        return call('late', 'save_workout', content=content())
    cid, _ = setup(a, slow)
    result = send(a, cid)
    assert result['status'] == 'failed' and result['error'] == 'model_timeout'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ConversationAction)) == 0


def test_late_model_response_is_rejected_before_tools(env, monkeypatch):
    from app.agent import runner
    from app.models import ConversationAction
    engine, (a, _) = env
    monkeypatch.setitem(runner.LIMITS, 'total_seconds', 0.05)
    def blocking(messages, tools):
        # A synchronous callback can overrun without yielding to cancellation.
        time.sleep(0.08)
        return call('late', 'save_workout', content=content())
    cid, _ = setup(a, blocking)
    result = send(a, cid)
    assert result['status'] == 'failed' and result['error'] == 'model_timeout'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ConversationAction)) == 0


def test_disabling_after_card_preserves_explicit_recording(env):
    engine, (a, _) = env
    cid, _ = setup(a, lambda messages, tools: call('save', 'save_workout', content=content()))
    card = send(a, cid)['result']
    write(a, '/exercise-preferences', {'items': [
        {'exercise_id': 'bench-press', 'version': 1, 'active': False}]}, 'PUT')
    result = write(a, '/conversation-actions/' + card['action_id'] + '/confirm', {'version': card['version']})
    assert result['status'] == 'confirmed'
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 1


def test_query_tool_result_feeds_final_reply(env):
    engine, (a, _) = env
    _, workout = make_workout(a)
    calls = {'n': 0}
    def model(messages, tools):
        calls['n'] += 1
        if calls['n'] == 1:
            assert any(schema['name'] == 'list_workouts' for schema in tools)
            return call('t1', 'list_workouts', on='2026-01-02')
        tools_messages = [m for m in messages if m.get('role') == 'tool']
        assert tools_messages and workout['id'] in tools_messages[-1]['content']
        return reply('你最近一次训练是 2026-01-02 的卧推。')
    cid, _ = setup(a, model)
    result = send(a, cid, '我最近练了什么？', mode='read')
    assert result['status'] == 'succeeded' and result['result'] == {'type': 'reply'}
    rows = messages_of(a, cid)
    assert [m['role'] for m in rows] == ['user', 'assistant', 'tool', 'assistant']
    assert rows[1]['tool_calls'][0]['name'] == 'list_workouts'
    assert rows[2]['tool_call_id'] == 't1'
    assert json.loads(rows[2]['content'])['ok'] is True
    assert rows[3]['content'].startswith('你最近一次训练')
    assert calls['n'] == 2


def test_read_batch_executes_every_call_and_feeds_all_results(env):
    engine, (a, _) = env
    _, workout = make_workout(a)
    def model(messages, tools):
        if not any(m.get('role') == 'tool' for m in messages):
            return ModelReply(type='tool_calls', calls=[
                ToolCallRequest(id='t1', name='list_workouts', arguments={'on': '2026-01-02'}),
                ToolCallRequest(id='t2', name='get_workout', arguments={'workout_id': workout['id']})])
        return reply('两个查询都完成了。')
    cid, provider = setup(a, model)
    result = send(a, cid, '看看我的训练', mode='read')
    assert result['result'] == {'type': 'reply'}
    rows = messages_of(a, cid)
    tool_rows = [m for m in rows if m['role'] == 'tool']
    assert [m['tool_call_id'] for m in tool_rows] == ['t1', 't2']
    assert all(json.loads(m['content'])['ok'] is True for m in tool_rows)
    # The next model round received every result, not just the first call's.
    second_round = provider.calls[1]['messages']
    assert [m['tool_call_id'] for m in second_round if m.get('role') == 'tool'] == ['t1', 't2']
    assert workout['id'] in second_round[-1]['content']


def test_budget_checked_before_every_model_call_with_capped_output(env, monkeypatch):
    from app.agent import context as context_module
    engine, (a, _) = env
    rounds = {'n': 0}
    def model(messages, tools):
        rounds['n'] += 1
        if rounds['n'] == 1:
            return call('t1', 'list_workouts', on='2026-01-02')
        return reply('完成')
    cid, provider = setup(a, model)
    checks, original = {'n': 0}, context_module.check_budget
    def counting(messages, schemas):
        checks['n'] += 1
        original(messages, schemas)
    monkeypatch.setattr(context_module, 'check_budget', counting)
    result = send(a, cid, '历史', mode='read')
    assert result['result'] == {'type': 'reply'}
    # The budget guard ran before both rounds (assemble also checks on round 1),
    # including the one after tool results.
    assert checks['n'] >= rounds['n'] >= 2
    # Output tokens stay within the reserved budget, never a fixed 16000.
    assert all(0 < c['max_tokens'] <= context_module.MAX_OUTPUT_TOKENS for c in provider.calls)


def test_write_tool_ends_turn_without_another_model_round(env):
    engine, (a, _) = env
    rounds = {'n': 0}
    def model(messages, tools):
        rounds['n'] += 1
        return call('t1', 'save_workout', content=content())
    cid, _ = setup(a, model)
    result = send(a, cid, '记录卧推')
    assert result['result']['type'] == 'confirmation_required'
    assert rounds['n'] == 1  # the runner stops; no polish round


def test_write_batch_with_multiple_calls_is_a_correctable_error(env):
    engine, (a, _) = env
    rounds = {'n': 0}
    def model(messages, tools):
        rounds['n'] += 1
        if rounds['n'] == 1:
            return ModelReply(type='tool_calls', calls=[
                ToolCallRequest(id='t1', name='save_workout', arguments={'content': content()}),
                ToolCallRequest(id='t2', name='delete_workout', arguments={'workout_id': 'x', 'expected_version': 1})])
        return reply('请确认要保存的内容。')
    cid, _ = setup(a, model)
    result = send(a, cid, '同时保存和删除')
    assert result['result'] == {'type': 'reply'}
    tool_rows = [m for m in messages_of(a, cid) if m['role'] == 'tool']
    assert len(tool_rows) == 2
    assert all('batch_write_single' in m['content'] for m in tool_rows)


def test_loop_budget_ends_runaway_turn(env):
    engine, (a, _) = env
    cid, _ = setup(a, lambda messages, tools: call('t' + str(len(messages)), 'list_workouts', on='2026-01-02'))
    result = send(a, cid, '历史')
    assert result['status'] == 'failed'
    assert result['error'] == 'agent_loop_limit'
    # Every round left a paired tool result; no dangling calls.
    rows = messages_of(a, cid)
    calls = {c['id'] for m in rows for c in (m['tool_calls'] or [])}
    results = {m['tool_call_id'] for m in rows if m['role'] == 'tool'}
    assert calls == results


def test_retry_keeps_failure_trace_without_duplicating_user_message(env):
    engine, (a, _) = env
    rounds = {'n': 0}
    def model(messages, tools):
        rounds['n'] += 1
        if rounds['n'] == 1:
            raise ProviderError('model_unavailable')
        return reply('恢复成功')
    cid, _ = setup(a, model)
    first = send(a, cid, '你好')
    assert first['status'] == 'failed'
    retry = a.post('/api/turns/' + first['id'] + '/retry', json={}, headers={'X-Request-ID': str(uuid4())})
    assert retry.status_code == 200, retry.text
    events = [json.loads(line[6:]) for line in retry.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['status'] == 'succeeded'
    rows = messages_of(a, cid)
    assert len([m for m in rows if m['role'] == 'user']) == 1
    assert rows[-1]['content'] == '恢复成功'
    # A later user message makes the failed turn permanently non-retryable.
    send(a, cid, '新的一句')
    write(a, '/turns/' + first['id'] + '/retry', {}, status=409)


def test_plain_message_keeps_pending_card_and_model_sees_it(env):
    """G13/G14: a plain message neither invalidates the card nor blocks it."""
    from app.core.database import write_transaction
    from app.models import ConversationAction, Turn, Workout, uid
    engine, (a, _) = env
    cid, _ = setup(a, lambda messages, tools: call('t1', 'save_workout', content=content()))
    first = send(a, cid, '记录卧推')
    action_id = first['result']['action_id']
    seen = {}
    def model(messages, tools):
        context_message = messages[1]['content']
        seen['pending'] = '"pending_action"' in context_message
        return reply('好的，先帮你查，之前的记录卡片仍可确认。')
    a.app.state.ai_provider = FakeProvider(model)
    second = send(a, cid, '顺便看看上周卧推')
    # The next model call still observes the pending action.
    assert seen == {'pending': True}
    assert second['result'] == {'type': 'reply'}
    with Session(engine) as db:
        assert db.get(ConversationAction, action_id).status == 'pending'
    # Simulate newer conversation content still processing.
    with write_transaction(engine) as db:
        action = db.get(ConversationAction, action_id)
        db.add(Turn(id=uid(), user_id=action.user_id, conversation_id=cid, token='x',
                    deadline=int(time.time()) + 100, context={}))
    # Confirm is paused while a turn runs; cancel stays possible.
    write(a, '/conversation-actions/' + action_id + '/confirm', {'version': first['result']['version']}, status=409)
    with write_transaction(engine) as db:
        running = db.scalars(select(Turn).where(Turn.conversation_id == cid, Turn.status == 'running')).all()
        for row in running:
            row.status = 'interrupted'
    result = write(a, '/conversation-actions/' + action_id + '/confirm', {'version': first['result']['version']})
    assert result['status'] == 'confirmed'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Workout)) == 1


def test_premature_proposal_is_rejected_with_reason(env):
    """Readiness check: missing critical content returns a structured tool error."""
    engine, (a, _) = env
    incomplete = {'actual_date': '2026-01-02', 'exercises': [{'exercise_id': 'bench-press', 'sets': [{'weight_kg': '60', 'reps': None}]}]}
    rounds = []
    def model(messages, tools):
        rounds.append(True)
        if len(rounds) == 1:
            return call('t1', 'save_workout', content=incomplete)
        error = json.loads(messages[-1]['content'])['error']
        assert error['code'] == 'missing_key_information'
        assert '次数' in error['field']
        assert '不要再次调用' not in error['message']
        return reply('还缺次数，请告诉我每组几次。')
    cid, _ = setup(a, model)
    assert send(a, cid, '记录卧推')['status'] == 'succeeded'
    with Session(engine) as db:
        from app.models import ConversationAction
        assert db.scalar(select(func.count()).select_from(ConversationAction)) == 0


def test_expired_turn_is_interrupted(env):
    engine, (a, _) = env
    from app.core.database import write_transaction
    from app.models import Turn
    def expire_lease_then_reply(messages, tools):
        with write_transaction(engine) as db:
            row = db.scalars(select(Turn).where(Turn.status == 'running')).one()
            row.deadline = int(time.time()) - 1
        return reply('晚了')
    cid, _ = setup(a, expire_lease_then_reply)
    result = send(a, cid, '你好')
    assert result['status'] == 'interrupted'
    assert result['error'] == 'execution_expired'
