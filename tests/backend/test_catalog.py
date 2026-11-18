"""Three-table catalog constraints, default activation and bounded SQL queries."""
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import write_transaction
from app.models import UserExercise, UserExercisePreference, User
from app.modules.catalog.service import list_exercises, query_exercises
from helpers import write


def test_new_custom_defaults_active_and_text_metadata_roundtrips(env):
    _, (a, b) = env
    row = write(a, '/exercises', {'name': '个人划船', 'equipment': '哑铃、训练凳',
                'primary_muscles': '背阔肌', 'secondary_muscles': '肱二头肌',
                'description': '保持躯干稳定', 'aliases': '自定义划船'})
    assert row['active'] is True and row['preference_version'] == 1
    assert row['equipment'] == '哑铃、训练凳'
    assert row['primary_muscles'] == '背阔肌'
    assert 'archived' not in row and 'available' not in row
    assert row in a.get('/api/exercises?active=true').json()['items']
    assert b.get('/api/exercises/' + row['id']).status_code == 404
    write(b, '/exercise-preferences', {'items': [
        {'exercise_id': row['id'], 'version': 1, 'active': True}]}, 'PUT', status=404)


def test_normalized_names_deduplicate_create_update_and_keep_user_scope(env):
    _, (a, b) = env
    first = write(a, '/exercises', {'name': 'ＤＢ   Row'})
    error = write(a, '/exercises', {'name': 'db row'}, status=409)
    assert error['detail']['code'] == 'exercise_name_taken'
    write(b, '/exercises', {'name': 'db row'})
    other = write(a, '/exercises', {'name': 'other'})
    write(a, '/exercises/' + other['id'], {'name': 'DB Row', 'version': 1}, 'PUT', status=409)
    assert a.get('/api/exercises/' + first['id']).json()['name'] == 'ＤＢ   Row'


def test_public_preferences_are_user_specific_and_reversible(env):
    _, (a, b) = env
    # Exercises without a preference default to active for every user.
    assert any(item['id'] == 'bench-press'
               for item in b.get('/api/exercises?active=true').json()['items'])
    write(a, '/exercise-preferences', {'items': [
        {'exercise_id': 'bench-press', 'version': 1, 'active': False}]}, 'PUT')
    assert all(item['id'] != 'bench-press'
               for item in a.get('/api/exercises?active=true').json()['items'])
    # A user-specific opt-out never affects other users.
    assert any(item['id'] == 'bench-press'
               for item in b.get('/api/exercises?active=true').json()['items'])
    write(a, '/exercise-preferences', {'items': [
        {'exercise_id': 'bench-press', 'version': 2, 'active': True}]}, 'PUT')
    assert any(item['id'] == 'bench-press'
               for item in a.get('/api/exercises?active=true').json()['items'])
    write(a, '/exercises/bench-press', {'name': 'changed', 'version': 1}, 'PUT', status=403)


def test_sql_pagination_search_and_complete_list_have_constant_queries(env):
    engine, (a, _) = env
    with write_transaction(engine) as db:
        user_id = db.scalar(select(User.id).where(User.username == 'alice'))
        for index in range(50):
            db.add(UserExercise(user_id=user_id, name=f'query {index:03d}', aliases='Search Alias'))
    statements = []
    def record(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(engine, 'before_cursor_execute', record)
    try:
        with Session(engine) as db:
            page = query_exercises(db, user_id, q='SEARCH alias', offset=10, limit=7)
            assert page['total'] == 50 and len(page['items']) == 7
            assert page['items'][0]['name'] == 'query 010'
            assert len(statements) == 2
            statements.clear()
            all_rows = list_exercises(db, user_id)
            assert len(all_rows) > 50 and len(statements) == 1
            statements.clear()
            assert len(list_exercises(db, user_id, active=True)) == len(all_rows)
            assert len(statements) == 1
            statements.clear()
            assert list_exercises(db, user_id, active=False) == []
            assert len(statements) == 1
            statements.clear()
            assert query_exercises(db, user_id, q='%')['total'] == 0
    finally:
        event.remove(engine, 'before_cursor_execute', record)


def test_database_target_unique_name_and_foreign_key_constraints(env):
    engine, (a, _) = env
    row = write(a, '/exercises', {'name': '约束动作'})
    with Session(engine) as db:
        user_id = db.scalar(select(User.id).where(User.username == 'alice'))
    invalid_targets = [dict(), dict(public_exercise_id='bench-press', user_exercise_id=row['id']),
                       dict(public_exercise_id='missing')]
    for values in invalid_targets:
        with pytest.raises(IntegrityError), write_transaction(engine) as db:
            db.add(UserExercisePreference(user_id=user_id, active=True, **values))
    with pytest.raises(IntegrityError), write_transaction(engine) as db:
        db.add(UserExercisePreference(user_id=user_id, user_exercise_id=row['id'], active=True))
    with pytest.raises(IntegrityError), write_transaction(engine) as db:
        db.add(UserExercise(user_id=user_id, name='约束动作'))
    with engine.connect() as connection:
        tables = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars())
        assert {'public_exercises', 'user_exercises', 'user_exercise_preferences'} <= tables
        assert 'exercises' not in tables and 'exercise_preferences' not in tables
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
        types = {row[1]: row[2] for row in connection.exec_driver_sql('PRAGMA table_info(public_exercises)')}
        assert types['equipment'] == 'TEXT' and types['primary_muscles'] == 'TEXT'


def test_training_custom_creation_reuses_name_and_defaults_active(env):
    _, (a, _) = env
    body = {'content': {'actual_date': '2026-01-02', 'exercises': [
        {'custom_name': '自定义训练动作', 'confirm_create': True, 'sets': [{'reps': 8}]},
        {'custom_name': '自定义训练动作', 'confirm_create': True, 'sets': [{'reps': 6}]},
    ]}}
    workout = write(a, '/workouts', body)
    entries = workout['content']['exercises']
    assert entries[0]['exercise_id'] == entries[1]['exercise_id']
    catalog = a.get('/api/exercises?active=true').json()['items']
    assert any(item['id'] == entries[0]['exercise_id'] for item in catalog)


def test_delete_unused_custom_exercise_removes_preference(env):
    from uuid import uuid4
    _, (a, _) = env
    row = write(a, '/exercises', {'name': '待删除动作'})
    result = write(a, '/exercises/' + row['id'], {'version': row['version']}, 'DELETE')
    assert result == {'removed': True}
    assert all(item['id'] != row['id'] for item in a.get('/api/exercises').json()['items'])
    assert a.get('/api/exercises/' + row['id']).status_code == 404


def test_delete_exercise_referenced_by_workout_is_rejected(env):
    from uuid import uuid4
    _, (a, _) = env
    body = {'content': {'actual_date': '2026-01-02', 'exercises': [
        {'custom_name': '在用动作', 'confirm_create': True, 'sets': [{'reps': 8}]},
    ]}}
    workout = write(a, '/workouts', body)
    exercise_id = workout['content']['exercises'][0]['exercise_id']
    row = a.get('/api/exercises/' + exercise_id).json()
    response = a.request('DELETE', '/api/exercises/' + exercise_id,
                         json={'version': row['version']},
                         headers={'X-Request-ID': str(uuid4())})
    assert response.status_code == 409, response.text
    assert response.json()['detail']['code'] == 'exercise_in_use'
    assert a.get('/api/exercises/' + exercise_id).status_code == 200


def test_equipment_categories(env):
    from helpers import write
    _, (client, other) = env
    item = write(client, '/user-equipment', {'name': '分类测试', 'category': '自由重量'})
    assert item['category'] == '自由重量'
    renamed = write(client, '/user-equipment/' + item['id'], {'name': '改名', 'version': item['version']}, method='PUT')
    assert renamed['category'] == '自由重量'
    assert any(row['id'] == item['id'] and row['category'] == '自由重量' for row in client.get('/api/user-equipment').json()['items'])
    assert all(row['id'] != item['id'] for row in other.get('/api/user-equipment').json()['items'])
    write(client, '/user-equipment', {'name': '非法分类', 'category': '不存在'}, status=422)
    linked = write(client, '/user-equipment', {'name': '哑铃', 'equipment_id': 'dumbbell'})
    assert linked['category'] == '自由重量'
