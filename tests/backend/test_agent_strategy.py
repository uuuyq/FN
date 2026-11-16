"""Execution policies and durable action-result continuations."""
import json

import pytest
from helpers import setup, send, write, content, call, reply
from app.agent.tools.registry import Tool, ToolRegistry
from app.agent.tools import ToolContext
from app.agent.tools.executor import run
from app.schemas import Schema


def test_direct_write_policy_is_independent_of_permissions():
    tool = Tool(name='calculate', description='test', model=Schema, kind='write',
                execution='direct', execute=lambda ctx, params: {'value': 42})
    registry = ToolRegistry([tool])
    ctx = ToolContext(db=None, user_id='user', conversation_id='chat', turn_id='turn', mode='edit')
    result = run(ctx, registry, 'calculate', {})
    assert result.data == {'value': 42}
    assert result.action is None and result.continuation == 'continue'
    ctx.mode = 'read'
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        run(ctx, registry, 'calculate', {})


@pytest.mark.parametrize('operation', ['confirm', 'cancel', 'conflict', 'failed'])
def test_action_result_continues_once_without_user_prompt(env, monkeypatch, operation):
    engine, (client, _) = env
    received = []

    def model(messages, tools):
        for message in reversed(messages):
            if message['role'] == 'tool':
                result = json.loads(message['content'])
                if result.get('data', {}).get('status'):
                    received.append(messages)
                    return reply('Outcome received')
        return call('save-call', 'save_workout', content=content())

    cid, provider = setup(client, model)
    turn = send(client, cid)
    action_id = turn['result']['action_id']
    if operation in ('conflict', 'failed'):
        from app.agent.tools import workouts
        from app.services import fail
        def broken(*args):
            fail(409 if operation == 'conflict' else 422, 'version_conflict')
        monkeypatch.setattr(workouts, 'execute_save', broken)
        # Registry constants hold the original callable.
        monkeypatch.setattr(workouts.SAVE_WORKOUT, 'execute', broken)
    decision = 'cancel' if operation == 'cancel' else 'confirm'
    response = write(client, f'/conversation-actions/{action_id}/{decision}', {'version': 1})
    continuation = response['result']['continuation_turn_id']
    stream = client.get(f'/api/turns/{continuation}/events')
    assert 'completed' in stream.text
    assert response['status'] == ('confirmed' if operation == 'confirm' else 'cancelled' if operation == 'cancel' else operation)
    assert len(received) == 1
    assert sum(m['role'] == 'user' for m in received[0]) == 2  # runtime context and original input
    final_tool = next(m for m in reversed(received[0]) if m['role'] == 'tool')
    assert final_tool['tool_call_id'] == 'save-call'
    assert json.loads(final_tool['content'])['data']['status'] == response['status']
    replay = write(client, f'/conversation-actions/{action_id}/{decision}', {'version': 1})
    assert replay['result']['continuation_turn_id'] == continuation
    assert len(received) == 1


@pytest.mark.parametrize('failure', ['provider', 'capacity'])
def test_continuation_retry_keeps_committed_workout(env, monkeypatch, failure):
    from app.agent import turns
    from app.agent.provider import ProviderError

    _, (client, _) = env
    outcomes = []
    fail_provider = failure == 'provider'

    def model(messages, tools):
        for message in reversed(messages):
            if message['role'] == 'tool':
                result = json.loads(message['content'])
                if result.get('data', {}).get('status') == 'confirmed':
                    outcomes.append(result)
                    if fail_provider:
                        return ProviderError('model_timeout')
                    return reply('Saved result received')
        return call('save-call', 'save_workout', content=content())

    cid, provider = setup(client, model)
    turn = send(client, cid)
    action_id = turn['result']['action_id']
    original_limit = turns.GLOBAL_RUNNING_LIMIT
    if failure == 'capacity':
        monkeypatch.setattr(turns, 'GLOBAL_RUNNING_LIMIT', 0)
    confirmed = write(client, f'/conversation-actions/{action_id}/confirm', {'version': 1})
    assert confirmed['status'] == 'confirmed'
    continuation = confirmed['result']['continuation_turn_id']
    client.get(f'/api/turns/{continuation}/events')
    failed = client.get(f'/api/turns/{continuation}').json()
    assert failed['status'] == 'failed'
    assert failed['error'] == ('model_timeout' if failure == 'provider' else 'model_capacity')
    saved = client.get('/api/workouts?on=2026-01-02').json()
    assert saved['total'] == 1
    workout_id = confirmed['result']['workout_id']
    assert saved['items'][0]['id'] == workout_id
    fail_provider = False
    monkeypatch.setattr(turns, 'GLOBAL_RUNNING_LIMIT', original_limit)
    response = client.post(f'/api/turns/{continuation}/retry', json={},
                           headers={'X-Request-ID': 'retry-continuation-' + failure})
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[-1]['id'] == continuation
    assert events[-1]['status'] == 'succeeded'
    saved_after = client.get('/api/workouts?on=2026-01-02').json()
    assert saved_after == saved
    assert outcomes[-1]['data']['result']['workout_id'] == workout_id
    snapshot = client.get(f'/api/conversations/{cid}').json()
    assert len(snapshot['actions']) == 1
    assert sum(message['role'] == 'user' for message in snapshot['messages']) == 1
    assert len(snapshot['turns']) == 2
