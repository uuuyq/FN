"""Undo uses committed business snapshots and preserves transaction atomicity."""
from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
from sqlalchemy import select
from app.core.database import write_transaction
from app.models import User, Conversation, Turn, Workout, AgentOperation, UserExercise
from app.agent.tools import ToolContext, build_registry
from app.agent import actions
from app.agent.operations import list_operations
from app.agent.tools.operations import ListOperations
from app.agent.tools.workouts import ListWorkouts, list_workouts
from app.modules.workouts.service import workout_view, purge_expired_workouts
from helpers import content


def context(db):
    user = db.scalar(select(User).where(User.username == 'alice'))
    conversation = Conversation(user_id=user.id, title='undo')
    db.add(conversation)
    db.flush()
    turn = Turn(user_id=user.id, conversation_id=conversation.id, status='succeeded', token='test', deadline=0, context={})
    db.add(turn)
    db.flush()
    return ToolContext(db, user.id, conversation.id, turn.id, 'edit')


def execute(ctx, name, **payload):
    tool = build_registry().get(name)
    params = tool.model.model_validate(payload)
    tool.validate(ctx, params)
    action = actions.propose(ctx, tool, params.model_dump(mode='json'))
    return actions.apply(ctx.db, ctx.user_id, action.id, 'confirm', action.version)


def editable(db, workout_id):
    value = deepcopy(workout_view(db, db.get(Workout, workout_id))['content'])
    value.pop('missing_information')
    for item in value['exercises']:
        item.pop('name')
    return value


@pytest.mark.parametrize('operation', ['create', 'update', 'delete'])
def test_undo_restores_and_replays(env, operation):
    engine, _ = env
    with write_transaction(engine) as db:
        ctx = context(db)
        created = execute(ctx, 'save_workout', content=content(), summary='记录卧推')
        wid = created['result']['workout_id']
        original = editable(db, wid)
        target = created
        if operation == 'update':
            changed = deepcopy(original)
            changed['exercises'][0]['sets'][0]['weight_kg'] = '70'
            target = execute(ctx, 'save_workout', content=changed, workout_id=wid, expected_version=1)
        elif operation == 'delete':
            target = execute(ctx, 'delete_workout', workout_id=wid, expected_version=1)
        undo = execute(ctx, 'undo_operation', operation_id=target['result']['operation_id'])
        assert undo['status'] == 'confirmed', undo
        row = db.get(Workout, wid)
        assert row.version == target['result'].get('version', 2) + 1
        if operation == 'create':
            assert row.deleted_at
        else:
            assert row.deleted_at is None
            assert editable(db, wid) == original
        replay = actions.apply(db, ctx.user_id, undo['action_id'], 'confirm', 1)
        assert replay['result'] == undo['result']
        history = list_operations(ctx, ListOperations())
        assert any(item['undone'] for item in history['items'])
        assert db.scalar(select(AgentOperation).where(AgentOperation.id == target['result']['operation_id'])).undo_action_id == undo['action_id']


@pytest.mark.parametrize('failure', ['conflict', 'expired', 'missing', 'foreign'])
def test_undo_rechecks_on_confirmation(env, failure):
    engine, _ = env
    with write_transaction(engine) as db:
        ctx = context(db)
        saved = execute(ctx, 'save_workout', content=content())
        oid = saved['result']['operation_id']
        tool = build_registry().get('undo_operation')
        payload = tool.model(operation_id=oid).model_dump(mode='json')
        action = actions.propose(ctx, tool, payload)
        row = db.get(AgentOperation, oid)
        workout = db.get(Workout, row.workout_id)
        if failure == 'conflict':
            workout.version += 1
        elif failure == 'expired':
            row.created_at = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        elif failure == 'missing':
            db.delete(workout)
        else:
            row.user_id = db.scalar(select(User.id).where(User.username == 'bob'))
        db.flush()
        result = actions.apply(db, ctx.user_id, action.id, 'confirm', 1)
        assert result['status'] in ('failed', 'conflict')
        assert row.undone_at is None


@pytest.mark.parametrize('during_undo', [False, True])
def test_partial_execution_rolls_back_with_history(env, monkeypatch, during_undo):
    from app.agent.tools import workouts
    from app.agent import operations
    engine, _ = env
    with write_transaction(engine) as db:
        ctx = context(db)
        if during_undo:
            saved = execute(ctx, 'save_workout', content=content())
            wid = saved['result']['workout_id']
            def broken(*args):
                operations.delete_workout_original(*args)
                raise RuntimeError('injected')
            monkeypatch.setattr(operations, 'delete_workout_original', operations.delete_workout, raising=False)
            monkeypatch.setattr(operations, 'delete_workout', broken)
            result = execute(ctx, 'undo_operation', operation_id=saved['result']['operation_id'])
            assert db.get(Workout, wid).deleted_at is None
            assert db.get(Workout, wid).version == 1
            assert db.get(AgentOperation, saved['result']['operation_id']).undone_at is None
        else:
            original = workouts.save_workout
            def broken(*args):
                original(*args)
                raise RuntimeError('injected')
            monkeypatch.setattr(workouts, 'save_workout', broken)
            result = execute(ctx, 'save_workout', content=content())
            assert db.scalar(select(Workout)) is None
            assert db.scalar(select(AgentOperation)) is None
        assert result['status'] == 'failed'


def test_custom_catalog_survives_undo_and_snapshots_expire(env):
    engine, _ = env
    with write_transaction(engine) as db:
        ctx = context(db)
        data = content()
        data['exercises'][0] = {**data['exercises'][0], 'exercise_id': None, 'custom_name': '个人动作'}
        saved = execute(ctx, 'save_workout', content=data)
        assert execute(ctx, 'undo_operation', operation_id=saved['result']['operation_id'])['status'] == 'confirmed'
        assert db.scalar(select(UserExercise).where(UserExercise.name == '个人动作')) is not None
        row = db.get(AgentOperation, saved['result']['operation_id'])
        row.before = {'test': True}
        row.created_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        purge_expired_workouts(db)
        assert row.before is None


def test_query_ranges_filters_and_pagination(env):
    engine, _ = env
    with write_transaction(engine) as db:
        ctx = context(db)
        for day in ['2026-01-02', '2026-01-03']:
            data = content()
            data['actual_date'] = day
            execute(ctx, 'save_workout', content=data)
        recent = list_workouts(ctx, ListWorkouts(exercise_id='bench-press', limit=1))
        assert recent['total'] == 2 and recent['has_more']
        assert recent['items'][0]['summary'].startswith('2026-01-03')
        assert list_workouts(ctx, ListWorkouts(on='2026-01-02'))['total'] == 1
        assert list_workouts(ctx, ListWorkouts(start_date='2026-01-03'))['total'] == 1
        assert list_workouts(ctx, ListWorkouts(end_date='2026-01-01'))['total'] == 0
        assert list_workouts(ctx, ListWorkouts(offset=1, limit=1))['has_more'] is False
        for args in [dict(on='2026-01-01', start_date='2026-01-01'), dict(start_date='2026-02-01', end_date='2026-01-01')]:
            with pytest.raises(ValueError):
                ListWorkouts(**args)


def test_competing_undo_and_summary_contract(env):
    engine, _ = env
    with write_transaction(engine) as db:
        ctx = context(db)
        saved = execute(ctx, 'save_workout', content=content(), summary='')
        assert '卧推' in saved['summary']
        registry = build_registry()
        for tool in registry.tools():
            if tool.kind == 'write':
                assert tool.model.model_fields['summary'].default is None
        tool = registry.get('undo_operation')
        payload = tool.model(operation_id=saved['result']['operation_id'], summary='撤销刚才的记录').model_dump(mode='json')
        first = actions.propose(ctx, tool, payload)
        # Model proposals normally supersede old cards. Independent persisted
        # proposals still must not execute the same undo twice.
        second = actions.propose(ctx, tool, payload)
        first.status = 'pending'
        db.flush()
        assert actions.apply(db, ctx.user_id, first.id, 'confirm', first.version)['status'] == 'confirmed'
        assert actions.apply(db, ctx.user_id, second.id, 'confirm', second.version)['status'] == 'conflict'


def test_failed_update_preserves_groups_and_operation_history(env, monkeypatch):
    from app.agent.tools import workouts
    engine, _ = env
    with write_transaction(engine) as db:
        ctx = context(db)
        saved = execute(ctx, 'save_workout', content=content())
        wid = saved['result']['workout_id']
        original = editable(db, wid)
        changed = deepcopy(original)
        changed['exercises'][0]['sets'][0]['reps'] = 10
        save = workouts.save_workout
        def broken(*args):
            save(*args)
            raise RuntimeError('after replacement')
        monkeypatch.setattr(workouts, 'save_workout', broken)
        assert execute(ctx, 'save_workout', content=changed, workout_id=wid, expected_version=1)['status'] == 'failed'
        assert editable(db, wid) == original
        assert db.get(Workout, wid).version == 1
        assert len(db.scalars(select(AgentOperation)).all()) == 1
