from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from helpers import write, content, make_workout
from app.core.database import write_transaction
from app.models import Workout, WorkoutSet, UserExercise
from app.modules.workouts.service import purge_expired_workouts


def editable(workout):
    data = deepcopy(workout['content'])
    for item in data['exercises']:
        item.pop('name')
    return data


def test_two_level_storage_and_current_names(env):
    engine, (a, b) = env
    custom = write(a, '/exercises', {'name': '个人卧推'})
    data = content()
    data['exercises'].append({'exercise_id': custom['id'], 'sets': [{'reps': 5, 'notes': '单侧重量'}]})
    data['exercises'].append(deepcopy(data['exercises'][0]))
    w = write(a, '/workouts', {'content': data})
    assert [e['exercise_id'] for e in w['content']['exercises']] == ['bench-press', custom['id'], 'bench-press']
    assert 'status' not in w
    write(a, '/exercises/' + custom['id'], {'version': 1, 'name': '改名卧推'}, 'PUT')
    write(a, '/exercise-preferences', {'items': [{'exercise_id': custom['id'], 'version': 1, 'active': False}]}, 'PUT')
    current = a.get('/api/workouts/' + w['id']).json()
    assert current['content']['exercises'][1]['name'] == '改名卧推'
    assert current['content']['exercises'][1]['sets'][0]['notes'] == '单侧重量'
    assert b.get('/api/workouts/' + w['id']).status_code == 404
    with Session(engine) as db:
        rows = db.scalars(select(WorkoutSet).where(WorkoutSet.workout_id == w['id'])).all()
        assert len(rows) == 7
        assert {r.exercise_position for r in rows} == {0, 1, 2}
    tables = inspect(engine).get_table_names()
    assert 'workout_exercises' not in tables and 'workout_drafts' not in tables


def test_history_edit_version_and_date_query(env):
    _, (a, b) = env
    _, w = make_workout(a)
    assert a.get('/api/workouts').status_code == 422
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 1
    assert a.get('/api/workouts?on=2026-01-03').json()['total'] == 0
    assert b.get('/api/workouts?on=2026-01-02').json()['total'] == 0
    data = editable(w)
    data['exercises'][0]['sets'][1]['reps'] = 5
    updated = write(a, '/workouts/' + w['id'], {'version': 1, 'content': data}, 'PUT')
    assert updated['version'] == 2
    assert updated['content']['exercises'][0]['sets'][1]['reps'] == 5
    assert updated['content']['exercises'][0]['sets'][0]['weight_kg'] == '60.125'
    assert updated['content']['exercises'][0]['sets'][-1]['reps'] is None
    assert [s['id'] for s in updated['content']['exercises'][0]['sets']] == [s['id'] for s in w['content']['exercises'][0]['sets']]
    write(a, '/workouts/' + w['id'], {'version': 1, 'content': data}, 'PUT', status=409)
    assert a.get('/api/workout-drafts').status_code == 404


def test_catalog_profile_equipment_isolation(env):
    _, (a, b) = env
    p = a.get('/api/profile').json()
    p['preferences'] = '增肌'
    write(a, '/profile', p, 'PUT')
    assert b.get('/api/profile').json()['preferences'] == ''
    custom = write(a, '/exercises', {'name': '个人划船', 'primary_muscles': '背阔肌'})
    write(a, '/exercise-preferences', {'items': [{'exercise_id': custom['id'], 'version': 1, 'active': True}]}, 'PUT')
    row = a.get('/api/exercises/' + custom['id']).json()
    assert row['active']
    write(a, '/exercise-preferences', {'items': [{'exercise_id': custom['id'], 'version': 2, 'active': False}]}, 'PUT')
    row = a.get('/api/exercises/' + custom['id']).json()
    assert not row['active']
    assert b.get('/api/exercises/' + custom['id']).status_code == 404
    eq = write(a, '/user-equipment', {'name': '家中弹力带'})
    write(a, '/user-equipment/' + eq['id'], {'name': '健身房弹力带', 'version': 1}, 'PUT')
    write(b, '/user-equipment/' + eq['id'], {'version': 2}, 'DELETE', status=404)
    write(a, '/user-equipment/' + eq['id'], {'version': 2}, 'DELETE')
    assert a.get('/api/user-equipment').json()['items'] == []


def test_idempotency_isolation_and_atomic_rollback(env):
    engine, (a, b) = env
    key = str(uuid4())
    body = {'content': content()}
    w = write(a, '/workouts', body, request_id=key)
    assert write(a, '/workouts', body, request_id=key) == w
    changed = content()
    changed['notes'] = 'changed'
    write(a, '/workouts', {'content': changed}, request_id=key, status=409)
    write(b, '/workouts/' + w['id'], {'version': 1, 'content': content()}, 'PUT', status=404)
    invalid = content()
    invalid['exercises'] = [
        {'custom_name': '回滚动作', 'confirm_create': True, 'sets': [{'reps': 3}]},
        {'custom_name': '未确认动作', 'sets': [{'reps': 1}]}]
    write(a, '/workouts/' + w['id'], {'version': 1, 'content': invalid}, 'PUT', status=422)
    assert a.get('/api/workouts/' + w['id']).json() == w
    with Session(engine) as db:
        assert db.scalar(select(UserExercise).where(UserExercise.name == '回滚动作')) is None
    # Another workout cannot take existing set IDs.
    write(a, '/workouts', {'content': editable(w)}, status=409)
    repeated = editable(w)
    repeated['exercises'][0]['sets'].append(repeated['exercises'][0]['sets'][0])
    write(a, '/workouts/' + w['id'], {'version': 1, 'content': repeated}, 'PUT', status=422)


def test_concurrent_save_with_same_request_id(env):
    _, (a, _) = env
    barrier = Barrier(2)
    key = str(uuid4())
    def save(_):
        with TestClient(a.app) as client:
            client.cookies.update(a.cookies)
            client.headers.update(a.headers)
            barrier.wait()
            return write(client, '/workouts', {'content': content()}, request_id=key)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, range(2)))
    assert results[0] == results[1]
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 1


def test_delete_and_scheduled_retention(env):
    engine, (a, b) = env
    _, w = make_workout(a)
    write(b, '/workouts/' + w['id'], {'version': 1}, 'DELETE', status=404)
    write(a, '/workouts/' + w['id'], {'version': 2}, 'DELETE', status=409)
    key = str(uuid4())
    write(a, '/workouts/' + w['id'], {'version': 1}, 'DELETE', request_id=key)
    write(a, '/workouts/' + w['id'], {'version': 1}, 'DELETE', request_id=key)
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 0
    assert a.get('/api/workouts/calendar?month=2026-01').json()['training_days'] == 0
    assert a.get('/api/workouts/' + w['id']).status_code == 404
    with write_transaction(engine) as db:
        row = db.get(Workout, w['id'])
        assert row.version == 2
        deleted = datetime.fromisoformat(row.deleted_at)
        assert purge_expired_workouts(db, at=deleted + timedelta(days=7, microseconds=-1)) == 0
        assert purge_expired_workouts(db, at=deleted + timedelta(days=7)) == 1
        assert db.get(Workout, w['id']) is None
        assert db.scalar(select(WorkoutSet).where(WorkoutSet.workout_id == w['id'])) is None
        assert db.execute(text('PRAGMA foreign_key_check')).all() == []


def test_reads_do_not_trigger_cleanup(env):
    engine, (a, _) = env
    _, w = make_workout(a)
    write(a, '/workouts/' + w['id'], {'version': 1}, 'DELETE')
    with write_transaction(engine) as db:
        db.get(Workout, w['id']).deleted_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 0
    assert a.get('/api/workouts/' + w['id']).status_code == 404
    with Session(engine) as db:
        assert db.get(Workout, w['id']) is not None
