from helpers import write, content, make_workout
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import write_transaction
from app.models import Workout, Exercise, WorkoutSet


def test_archived_exercises_only_allowed_for_retained_history(env):
    from copy import deepcopy
    engine, (a, _) = env
    _, w = make_workout(a)
    with write_transaction(engine) as db:
        db.get(Exercise, 'bench-press').archived = True
    # History remains queryable, including archived exercises.
    assert a.get('/api/workouts/' + w['id']).status_code == 200
    assert a.get('/api/workouts?exercise_id=bench-press').json()['total'] == 1
    c = deepcopy(w['content'])
    c['exercises'][0].pop('name_snapshot')
    c['exercises'][0]['sets'][0]['reps'] = 10
    saved = write(a, '/workouts/' + w['id'], {'version': 1, 'content': c}, 'PUT')
    assert saved['content']['exercises'][0]['sets'][0]['reps'] == 10
    # A new exercise entry cannot reuse an archived reference, even in this workout.
    c['exercises'].append(deepcopy(c['exercises'][0]))
    c['exercises'][-1]['id'] = None
    for group in c['exercises'][-1]['sets']:
        group['id'] = None
    rejected = write(a, '/workouts/' + w['id'], {'version': 2, 'content': c}, 'PUT', status=409)
    assert rejected['detail']['code'] == 'exercise_archived'
    # New workouts are also rejected at the final shared save boundary.
    draft = write(a, '/workout-drafts', {'content': content()})
    write(a, '/workout-drafts/' + draft['id'] + '/confirm', {'version': draft['version']}, status=409)


def test_replacing_historical_entry_with_archived_exercise_is_rejected(env):
    engine, (a, _) = env
    _, w = make_workout(a)
    with write_transaction(engine) as db:
        db.get(Exercise, 'squat').archived = True
    c = w['content']
    c['exercises'][0].pop('name_snapshot')
    c['exercises'][0]['exercise_id'] = 'squat'
    write(a, '/workouts/' + w['id'], {'version': 1, 'content': c}, 'PUT', status=409)


def test_manual_shared_draft_cancel_no_workout(env):
    _, (a, _) = env
    draft = write(a, '/workout-drafts', {'content': content()})
    assert a.get('/api/workouts').json()['total'] == 0
    draft['content']['exercises'][0]['sets'][-1]['reps'] = 5
    updated = write(a, '/workout-drafts/' + draft['id'], {'version': 1, 'content': draft['content']}, 'PUT')
    assert a.get('/api/workout-drafts/' + draft['id']).json()['content'] == updated['content']
    write(a, '/workout-drafts/' + draft['id'] + '/cancel', {'version': 2})
    write(a, '/workout-drafts/' + draft['id'] + '/cancel', {'version': 2})
    write(a, '/workout-drafts/' + draft['id'] + '/confirm', {'version': 3}, status=409)
    assert a.get('/api/workouts').json()['total'] == 0


def test_history_edit_and_soft_delete(env):
    _, (a, _) = env
    draft, w = make_workout(a)
    duplicate = write(a, '/workout-drafts/' + draft['id'] + '/confirm', {'version': 1})
    assert duplicate['id'] == w['id']
    assert a.get('/api/workouts?on=2026-01-02').json()['total'] == 1
    assert a.get('/api/workouts?start=2026-01-01&end=2026-01-03&exercise_id=bench-press&limit=1').json()['items'][0]['id'] == w['id']
    assert a.get('/api/workouts?on=2026-01-03').json()['total'] == 0
    ids = [s['id'] for s in w['content']['exercises'][0]['sets']]
    c = w['content']
    c['exercises'][0].pop('name_snapshot')
    c['exercises'][0]['sets'][1]['reps'] = 5
    updated = write(a, '/workouts/' + w['id'], {'version': 1, 'content': c}, 'PUT')
    assert [s['id'] for s in updated['content']['exercises'][0]['sets']] == ids
    assert updated['content']['exercises'][0]['sets'][0]['weight_kg'] == '60.125'
    assert updated['content']['exercises'][0]['sets'][-1]['reps'] is None
    write(a, '/workouts/' + w['id'], {'version': 1, 'content': c}, 'PUT', status=409)
    write(a, '/workouts/' + w['id'], {'version': 2}, 'DELETE')
    assert a.get('/api/workouts').json()['total'] == 0
    assert a.get('/api/workouts/' + w['id']).status_code == 404


def test_catalog_profile_equipment_isolation(env):
    _, (a, b) = env
    p = a.get('/api/profile').json()
    p['goal'] = '增肌'
    write(a, '/profile', p, 'PUT')
    assert b.get('/api/profile').json()['goal'] == ''
    custom = write(a, '/exercises', {'name': '个人划船', 'muscles': ['背阔肌']})
    write(a, '/exercise-preferences', {'items': [{'exercise_id': custom['id'], 'version': 1, 'available': True}]}, 'PUT')
    row = a.get('/api/exercises/' + custom['id']).json()
    assert row['effective_selected']
    write(a, '/exercise-preferences', {'items': [{'exercise_id': custom['id'], 'version': 2, 'available': False}]}, 'PUT')
    row = a.get('/api/exercises/' + custom['id']).json()
    assert not row['available'] and not row['effective_selected']
    assert b.get('/api/exercises/' + custom['id']).status_code == 404
    eq = write(a, '/user-equipment', {'name': '家中弹力带'})
    write(a, '/user-equipment/' + eq['id'], {'name': '健身房弹力带', 'version': 1}, 'PUT')
    write(b, '/user-equipment/' + eq['id'], {'version': 2}, 'DELETE', status=404)
    write(a, '/user-equipment/' + eq['id'], {'version': 2}, 'DELETE')
    assert a.get('/api/user-equipment').json()['items'] == []


def test_security_idempotency_and_rollback(env):
    engine, (a, b) = env
    draft, w = make_workout(a)
    assert b.get('/api/workouts/' + w['id']).status_code == 404
    assert b.get('/api/workout-drafts/' + draft['id']).status_code == 404
    write(b, '/workout-drafts', {'original_id': w['id']}, status=404)
    assert a.put('/api/profile', json={'version': 1, 'goal': 'test'}, headers={'X-CSRF-Token': ''}).status_code == 403
    key = str(uuid4())
    first = write(a, '/exercises', {'name': '幂等动作'}, request_id=key)
    assert write(a, '/exercises', {'name': '幂等动作'}, request_id=key)['id'] == first['id']
    write(a, '/exercises', {'name': '其他动作'}, request_id=key, status=409)
    c = content()
    c['exercises'] = [{'custom_name': '回滚动作', 'confirm_create': True, 'sets': [{'reps': 3}]}, {'custom_name': '未确认动作', 'sets': [{'reps': 1}]}]
    d = write(a, '/workout-drafts', {'content': c})
    write(a, '/workout-drafts/' + d['id'] + '/confirm', {'version': 1}, status=422)
    with Session(engine) as db:
        assert db.scalar(select(Exercise).where(Exercise.name == '回滚动作')) is None
    assert a.get('/api/workout-drafts/' + d['id']).json()['status'] == 'editable'
    assert a.get('/api/workouts').json()['total'] == 1
    a.post('/api/auth/logout')
    assert a.get('/api/auth/me').status_code == 401


def test_original_version_and_snapshot(env):
    _, (a, _) = env
    _, w = make_workout(a)
    d1 = write(a, '/workout-drafts', {'original_id': w['id']})
    d2 = write(a, '/workout-drafts', {'original_id': w['id']})
    write(a, '/workout-drafts/' + d1['id'] + '/confirm', {'version': 1})
    write(a, '/workout-drafts/' + d2['id'] + '/confirm', {'version': 1}, status=409)


def test_concurrent_confirmation_and_constraints(env):
    engine, (a, _) = env
    d = write(a, '/workout-drafts', {'content': content()})
    barrier = Barrier(2)
    def confirm(_):
        with TestClient(a.app) as c:
            c.cookies.update(a.cookies)
            c.headers.update(a.headers)
            barrier.wait()
            return write(c, '/workout-drafts/' + d['id'] + '/confirm', {'version': 1})
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(confirm, range(2)))
    assert results[0]['id'] == results[1]['id']
    assert a.get('/api/workouts').json()['total'] == 1
    with engine.connect() as c1, engine.connect() as c2:
        assert c1.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
        assert c2.exec_driver_sql('PRAGMA journal_mode').scalar() == 'wal'
        assert c2.exec_driver_sql('PRAGMA busy_timeout').scalar() == 5000
        with pytest.raises(IntegrityError):
            c1.execute(text("INSERT INTO exercise_preferences (user_id,exercise_id,available,version) VALUES ('missing','bench-press',1,1)"))


def test_retention_and_closed_record_isolation(env):
    from datetime import datetime, timedelta, timezone
    from app.models import WorkoutExercise, WorkoutDraft
    from app.modules.workouts.service import purge_expired_workouts
    engine, (a, b) = env
    draft, w = make_workout(a)
    write(b, '/workouts/' + w['id'], {'version': 1}, 'DELETE', status=404)
    write(a, '/workouts/' + w['id'], {'version': 2}, 'DELETE', status=409)
    request_id = str(uuid4())
    write(a, '/workouts/' + w['id'], {'version': 1}, 'DELETE', request_id=request_id)
    write(a, '/workouts/' + w['id'], {'version': 1}, 'DELETE', request_id=request_id)
    assert a.get('/api/workouts').json()['total'] == 0
    assert a.get('/api/workouts/calendar?month=2026-01').json()['training_days'] == 0
    assert a.get('/api/workouts/' + w['id']).status_code == 404
    write(a, '/workout-drafts', {'original_id': w['id']}, status=404)
    write(a, '/workout-drafts/' + draft['id'] + '/confirm', {'version': 1}, status=404)
    with write_transaction(engine) as db:
        row = db.get(Workout, w['id'])
        assert row.status == 'closed' and row.version == 2
        deleted = datetime.fromisoformat(row.deleted_at)
        assert purge_expired_workouts(db, at=deleted + timedelta(days=7, microseconds=-1)) == 0
        assert db.get(WorkoutSet, w['content']['exercises'][0]['sets'][0]['id']) is not None
        assert purge_expired_workouts(db, at=deleted + timedelta(days=7)) == 1
        assert db.get(Workout, w['id']) is None
        assert db.get(WorkoutExercise, w['content']['exercises'][0]['id']) is None
        assert db.get(WorkoutSet, w['content']['exercises'][0]['sets'][0]['id']) is None
        assert db.get(WorkoutDraft, draft['id']).result_id is None
        assert db.execute(text('PRAGMA foreign_key_check')).all() == []


def test_reads_leave_expired_records_for_scheduled_cleanup(env):
    from datetime import datetime, timedelta, timezone
    engine, (a, _) = env
    _, w = make_workout(a)
    write(a, '/workouts/' + w['id'], {'version': 1}, 'DELETE')
    with write_transaction(engine) as db:
        db.get(Workout, w['id']).deleted_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    assert a.get('/api/workouts').json()['total'] == 0
    assert a.get('/api/workouts/calendar?month=2026-01').json()['training_days'] == 0
    assert a.get('/api/workouts/' + w['id']).status_code == 404
    with Session(engine) as db:
        assert db.get(Workout, w['id']) is not None
