import json
import time
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.models import UserExercise, Workout, UserExercisePreference
from helpers import reply, send, setup, write
from app.agent.contracts import ModelReply, ToolCallRequest


def exercise_call(call_id):
    return ModelReply(type="tool_calls", calls=[ToolCallRequest(id=call_id, name="add_exercise", arguments={"name": "T杠划船", "training_parts": ["背"]})])


@pytest.mark.parametrize('decision', ['confirm', 'cancel'])
def test_add_exercise_only_creates_catalog_entry_after_confirm(env, decision):
    engine, (client, other) = env
    def model(messages, tools):
        if messages[-1]['role'] == 'tool':
            outcome = json.loads(messages[-1]['content'])
            assert outcome['data']['status'] == ('confirmed' if decision == 'confirm' else 'cancelled')
            return reply('已处理。')
        return exercise_call('add-motion')
    cid, _ = setup(client, model)
    turn = send(client, cid, '新增个人动作T杠划船')
    assert turn['result']['operation'] == 'add_exercise'
    assert turn['result']['details']['name'] == 'T杠划船'
    assert 'content' not in turn['result']['details']
    for field in ('aliases', 'primary_muscles', 'secondary_muscles', 'equipment', 'description'):
        assert turn['result']['details'][field] == ''
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UserExercise)) == 0
    result = write(client, '/conversation-actions/' + turn['result']['action_id'] + '/' + decision, {'version': 1})
    deadline = time.monotonic() + 5
    while True:
        history = client.get('/api/conversations/' + cid).json()
        continuation = next(t for t in history['turns'] if t['id'] == result['result']['continuation_turn_id'])
        if continuation['status'] != 'running':
            break
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert continuation['status'] == 'succeeded'
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Workout)) == 0
        assert db.scalar(select(func.count()).select_from(UserExercise)) == (1 if decision == 'confirm' else 0)
        if decision == 'confirm':
            exercise = db.scalar(select(UserExercise))
            assert exercise.training_parts == ['背']
            assert db.scalar(select(UserExercisePreference).where(UserExercisePreference.user_exercise_id == exercise.id)).active
            assert other.get('/api/exercises/' + exercise.id).status_code == 404
    if decision == 'confirm':
        cid, _ = setup(client, lambda messages, tools: exercise_call('duplicate')
            if messages[-1]['role'] == 'user' else reply('动作已存在。'))
        turn = send(client, cid, '再次新增同名动作')
        assert turn['result']['type'] == 'reply'
        assert client.get('/api/conversations/' + cid).json()['actions'] == []
