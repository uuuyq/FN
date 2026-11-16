"""Regressions for partial agent profile edits and decided tool results."""
import json
import time
import pytest
from helpers import call, reply, send, setup, write


@pytest.mark.parametrize('decision', ['confirm', 'cancel'])
@pytest.mark.parametrize('interleaved', [False, True])
def test_sparse_profile_edit_and_decision_continuation(env, decision, interleaved):
    _, (client, _) = env
    original = client.get('/api/profile').json()
    original = write(client, '/profile', {**original, 'days_per_week': 5,
        'minutes_per_session': 70, 'preferences': '原有偏好'}, 'PUT')
    observed = []
    def model(messages, tools):
        if messages[-1].get('content') == '解释一下当前方案':
            return reply('当前方案可以继续调整。')
        if messages[-1]['role'] == 'tool' or (messages[-1].get('content') or '').startswith('[服务端操作结果]'):
            tool_message = next(m for m in reversed(messages) if m['role'] == 'tool')
            result = json.loads(tool_message['content'])
            assert result['ok'] is True
            assert result['data']['status'] == ('confirmed' if decision == 'confirm' else 'cancelled')
            assert 'error' not in result
            ids = [c['id'] for m in messages for c in m.get('tool_calls', [])]
            assert tool_message['tool_call_id'] in ids
            assert messages[-1]['role'] in ('tool', 'user')
            thought = next(m for m in messages if m.get('tool_calls'))
            assert thought['reasoning_content'] == 'synthetic internal metadata'
            assert len([m for m in messages if m.get('tool_call_id') == 'profile-edit']) == 1
            assert not any(m['role'] == 'assistant' and (m.get('content') or '').startswith('[服务端操作结果]') for m in messages)
            observed.append(result)
            return reply('已处理，可以继续调整计划。')
        response = call('profile-edit', 'update_profile', version=original['version'],
                    preferences='两个主要动作和一个辅助动作')
        response.reasoning_content = 'synthetic internal metadata'
        return response
    cid, _ = setup(client, model)
    turn = send(client, cid, '保存为个人偏好')
    action_id = turn['result']['action_id']
    details = turn['result']['details']
    assert details['after']['days_per_week'] == 5
    assert details['after']['minutes_per_session'] == 70
    assert 'summary' not in details['after']
    if interleaved:
        send(client, cid, '解释一下当前方案')
    result = write(client, '/conversation-actions/' + action_id + '/' + decision, {'version': 1})
    continuation = result['result']['continuation_turn_id']
    deadline = time.monotonic() + 5
    while True:
        history = client.get('/api/conversations/' + cid).json()
        latest = next(t for t in history['turns'] if t['id'] == continuation)
        if latest['status'] != 'running':
            break
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert latest['status'] == 'succeeded'
    assert observed
    assert all('reasoning_content' not in (m.get('event_data') or {}) for m in history['messages'])
    profile = client.get('/api/profile').json()
    assert profile['days_per_week'] == 5 and profile['minutes_per_session'] == 70
    assert profile['preferences'] == ('两个主要动作和一个辅助动作' if decision == 'confirm' else '原有偏好')


def test_explicit_null_clears_only_requested_profile_field(env):
    from types import SimpleNamespace
    from sqlalchemy import select
    from app.models import User
    from app.core.database import write_transaction
    from app.agent.tools.profile import UpdateProfile, execute_update
    engine, _ = env
    with write_transaction(engine) as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.profile = {'days_per_week': 5, 'minutes_per_session': 70}
        ctx = SimpleNamespace(db=db, user_id=user.id)
        result = execute_update(ctx, UpdateProfile(version=user.profile_version, minutes_per_session=None))
        assert result['days_per_week'] == 5
        assert result['minutes_per_session'] is None
