"""Regression coverage for tools using the current split catalog and flat sets."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.agent.context import runtime_context
from app.agent.tools.catalog import UpdatePreferences, validate_preferences, execute_preferences
from app.agent.tools.profile import update_summary, update_details, get_profile
from app.agent.tools.workouts import SaveWorkout, validate_save, execute_save, get_workout, GetWorkout
from app.core.database import write_transaction
from app.models import User, UserExercise, UserEquipment, Equipment
from helpers import content


def test_profile_card_uses_same_defaults_as_runtime_context(env):
    engine, _ = env
    with write_transaction(engine) as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        ctx = SimpleNamespace(db=db, user_id=user.id)
        profile = get_profile(ctx, None)
        assert 'profile' not in runtime_context(db, user.id, 'edit')
        assert update_summary(ctx, profile) == '更新个人条件'
        details = update_details(ctx, profile)
        assert details['before'] == details['after']


def test_preference_validation_rejects_duplicate_targets_before_card(env):
    engine, _ = env
    with write_transaction(engine) as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        ctx = SimpleNamespace(db=db, user_id=user.id)
        item = {'exercise_id': 'bench-press', 'version': 1, 'active': True}
        with pytest.raises(HTTPException) as caught:
            validate_preferences(ctx, UpdatePreferences(items=[item, item]))
        assert caught.value.detail['code'] == 'duplicate_exercise'


def test_private_catalog_preferences_and_flat_workout_sets(env):
    engine, _ = env
    with write_transaction(engine) as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        other = db.scalar(select(User).where(User.username == 'bob'))
        private = UserExercise(user_id=user.id, name='私有训练动作')
        db.add(private)
        db.flush()
        ctx = SimpleNamespace(db=db, user_id=user.id, mode='edit')
        params = UpdatePreferences(items=[{'exercise_id': private.id, 'active': False, 'version': 1}])
        validate_preferences(ctx, params)
        updated = execute_preferences(ctx, params)['items'][0]
        assert updated['id'] == private.id and updated['preference_version'] == 2
        # Inactive availability is a selection preference, and does not remove history access.
        data = content()
        data['exercises'][0]['exercise_id'] = private.id
        save = SaveWorkout(content=data)
        validate_save(ctx, save)
        receipt = execute_save(ctx, save)
        view = get_workout(ctx, GetWorkout(workout_id=receipt['workout_id']))
        groups = view['content']['exercises'][0]['sets']
        assert view['content']['exercises'][0]['name'] == private.name
        assert groups[0]['weight_kg'] == '60.125'
        changed = {key: value for key, value in view['content'].items() if key != 'missing_information'}
        for exercise in changed['exercises']:
            exercise.pop('name')
        changed['exercises'][0]['sets'][0]['reps'] = 9
        update = SaveWorkout(content=changed, workout_id=view['id'], expected_version=view['version'])
        validate_save(ctx, update)
        execute_save(ctx, update)
        latest = get_workout(ctx, GetWorkout(workout_id=view['id']))
        assert [group['id'] for group in latest['content']['exercises'][0]['sets']] == [group['id'] for group in groups]
        assert latest['version'] == 2
        foreign = SimpleNamespace(db=db, user_id=other.id, mode='edit')
        with pytest.raises(HTTPException) as caught:
            validate_preferences(foreign, UpdatePreferences(items=[{'exercise_id': private.id, 'active': True, 'version': 2}]))
        assert caught.value.status_code == 404


def test_equipment_context_keeps_public_reference(env):
    engine, _ = env
    with write_transaction(engine) as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        equipment = db.scalar(select(Equipment))
        db.add(UserEquipment(user_id=user.id, equipment_id=equipment.id, name=equipment.name))
        db.flush()
        runtime = runtime_context(db, user.id, 'edit')
        assert runtime['equipment'][0]['equipment_id'] == equipment.id


@pytest.mark.parametrize('status,receipt', [
    ('confirmed', {'workout_id': 'workout-1', 'version': 3, 'summary': '保存完成'}),
    ('cancelled', None),
    ('failed', {'error': {'code': 'internal_error', 'message': '执行失败。'}}),
])
def test_execution_result_context_preserves_structured_receipt(env, status, receipt):
    import json
    from helpers import reply, send, setup
    from app.agent.conversations import add_message
    from app.models import Message
    engine, (client, _) = env
    cid, _ = setup(client, lambda messages, tools: reply('收到'))
    turn = send(client, cid, '记录情况')
    result = {'action_id': 'action-1', 'tool_name': 'save_workout', 'status': status, 'result': receipt}
    pending = json.dumps({'ok': True, 'data': {'confirmation_required': True, 'action_id': 'action-1'}})
    with write_transaction(engine) as db:
        add_message(db, cid, turn['id'], 'assistant', tool_calls=[
            {'id': 'call-1', 'name': 'save_workout', 'arguments': {}}])
        original = add_message(db, cid, turn['id'], 'tool', content=pending, tool_call_id='call-1')
        add_message(db, cid, turn['id'], 'event', content='', event_kind='action_result', event_data=result)
        from app.agent.context import assemble
        messages = assemble(db, cid, {}, [])
        tool_messages = [message for message in messages if message['role'] == 'tool']
        assert len(tool_messages) == 1
        outcome = json.loads(tool_messages[0]['content'])
        assert outcome['ok'] == (status in ('confirmed', 'cancelled'))
        assert outcome['data'] == {'status': status, 'action_id': 'action-1', 'result': receipt}
        assert tool_messages[0]['tool_call_id'] == 'call-1'
        assert messages[-1]['role'] == 'tool'
        if status == 'failed':
            assert outcome['error'] == receipt['error']
        stored = db.scalar(select(Message).where(Message.tool_call_id == 'call-1'))
        assert stored.content == pending
