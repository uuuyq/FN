"""The single initial migration creates the current schema."""
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[2] / 'backend'


def _make_config(path):
    config = Config(str(BACKEND / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND / 'migrations'))
    config.set_main_option('sqlalchemy.url', 'sqlite:///' + path.as_posix())
    return config


def _upgrade(config, target):
    command.upgrade(config, target)


def test_initial_schema_matches_models_and_repeated_prepare_preserves_data(tmp_path, monkeypatch):
    from sqlalchemy import inspect
    from sqlalchemy.orm import Session
    from app.core.database import make_engine, write_transaction
    from app.models import User, Workout, WorkoutSet, PublicExercise
    from scripts.seed import seed

    path = tmp_path / 'initial.db'
    config = _make_config(path)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())
    assert [revision.revision for revision in revisions] == ['0001']
    _upgrade(config, 'head')
    engine = make_engine('sqlite:///' + path.as_posix())
    seed(engine)
    with write_transaction(engine) as db:
        user = User(username='initial-test', password_hash='x')
        db.add(user)
        db.flush()
        workout = Workout(user_id=user.id, actual_date='2026-01-02')
        db.add(workout)
        db.flush()
        group = WorkoutSet(workout_id=workout.id, public_exercise_id='bench-press',
                           exercise_position=0, set_position=0, kind='working',
                           weight_grams=60000, reps=8, notes='总重量')
        db.add(group)
        db.flush()
        user_id, workout_id, group_id = user.id, workout.id, group.id
    _upgrade(config, 'head')
    command.check(config)
    with Session(engine) as db:
        assert db.get(User, user_id) is not None
        assert db.get(Workout, workout_id) is not None
        assert db.get(WorkoutSet, group_id).weight_grams == 60000
        assert db.get(PublicExercise, 'bench-press') is not None
        assert db.connection().exec_driver_sql('PRAGMA foreign_key_check').all() == []
    names = inspect(engine).get_table_names()
    assert 'workout_exercises' not in names and 'workout_drafts' not in names
    engine.dispose()


def test_new_schema_accepts_tool_history(tmp_path):
    path = tmp_path / 'fresh.db'
    config = _make_config(path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
        _upgrade(config, 'head')
        from app.core.database import make_engine, write_transaction
        from app.models import (User, Conversation, Turn, Message, uid, now)
        engine = make_engine('sqlite:///' + path.as_posix())
        with write_transaction(engine) as db:
            user = User(username='agent', password_hash='x')
            db.add(user)
            db.flush()
            conversation = Conversation(user_id=user.id, title='新对话')
            db.add(conversation)
            db.flush()
            turn = Turn(user_id=user.id, conversation_id=conversation.id, token='t', deadline=1,
                        context={'mode': 'edit'})
            db.add(turn)
            db.flush()
            # Multiple assistant/tool messages per turn are now valid.
            db.add(Message(conversation_id=conversation.id, turn_id=turn.id, role='user', content='记录', sequence=1))
            db.add(Message(conversation_id=conversation.id, turn_id=turn.id, role='assistant',
                           content='', tool_calls=[{'id': 'c1', 'name': 'list_workouts', 'arguments': {}}], sequence=2))
            db.add(Message(conversation_id=conversation.id, turn_id=turn.id, role='tool',
                           content='{"ok": true}', tool_call_id='c1', sequence=3))
            db.add(Message(conversation_id=conversation.id, turn_id=turn.id, role='assistant', content='完成', sequence=4))
            db.add(Message(conversation_id=conversation.id, turn_id=turn.id, role='event',
                           content='已确认', event_kind='action_confirmed', event_data={}, sequence=5))
        engine.dispose()


@pytest.mark.parametrize('revision', ['0001', '0005'])
def test_consolidated_upgrade_preserves_existing_rows(tmp_path, monkeypatch, revision):
    import sqlite3
    from sqlalchemy.orm import Session
    from app.core.database import make_engine, write_transaction
    from app.models import User, Workout, WorkoutSet, UserExercise
    from scripts.seed import seed

    path = tmp_path / 'existing.db'
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
    config = _make_config(path)
    command.upgrade(config, 'head')
    engine = make_engine('sqlite:///' + path.as_posix())
    seed(engine)
    with write_transaction(engine) as db:
        user = User(username='history', password_hash='unchanged-hash', onboarding_dismissed=False)
        db.add(user)
        db.flush()
        personal = UserExercise(user_id=user.id, name='个人动作', category='背部', training_parts=['背'])
        db.add(personal)
        workout = Workout(user_id=user.id, actual_date='2025-01-02', notes='历史训练')
        db.add(workout)
        db.flush()
        db.add(WorkoutSet(workout_id=workout.id, user_exercise_id=personal.id,
                          exercise_position=0, set_position=0, kind='working',
                          weight_grams=32125, reps=12, notes='历史组'))
        user_id = user.id
    engine.dispose()
    with sqlite3.connect(path) as db:
        if revision == '0001':
            for table, column in [('public_exercises', 'training_parts'),
                                  ('user_exercises', 'training_parts'), ('users', 'onboarding_dismissed')]:
                db.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
        db.execute('UPDATE alembic_version SET version_num = ?', (revision,))
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'")]
        before = {}
        for table in tables:
            cursor = db.execute(f'SELECT * FROM "{table}" ORDER BY rowid')
            before[table] = ([column[0] for column in cursor.description], cursor.fetchall())
    command.upgrade(config, 'head')
    command.upgrade(config, 'head')
    command.check(config)
    with sqlite3.connect(path) as db:
        for table, (columns, rows) in before.items():
            projection = ','.join('"' + column + '"' for column in columns)
            assert db.execute(f'SELECT {projection} FROM "{table}" ORDER BY rowid').fetchall() == rows
        assert db.execute('SELECT onboarding_dismissed FROM users WHERE id = ?', (user_id,)).fetchone()[0] == (1 if revision == '0001' else 0)
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
