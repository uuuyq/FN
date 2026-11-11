"""Migration 0010: conversation data cleared, business data preserved."""
import pytest
from alembic import command
from alembic.config import Config
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / 'backend'


def _upgrade(config, target):
    command.upgrade(config, target)


def _make_config(path):
    config = Config(str(BACKEND / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND / 'migrations'))
    config.set_main_option('sqlalchemy.url', 'sqlite:///' + path.as_posix())
    return config


def seed_old_database(path):
    """Build a 0009-shape database with the seed catalog plus legacy rows."""
    config = _make_config(path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
        _upgrade(config, '0009')
        from app.core.database import make_engine, write_transaction
        from scripts.seed import seed
        engine = make_engine('sqlite:///' + path.as_posix())
        seed(engine)
        with write_transaction(engine) as db:
            from sqlalchemy import text
            user_id, workout_id, draft_id, conversation_id, turn_id = ('id-user', 'id-workout', 'id-draft', 'id-conversation', 'id-turn')
            db.execute(text("INSERT INTO users (id, username, password_hash, profile, profile_version, ai_config, ai_config_version) VALUES ('id-user', 'legacy', 'x', '{}', 1, NULL, 1)"))
            db.execute(text("INSERT INTO workouts (id, user_id, actual_date, notes, created_at, status, version) VALUES ('id-workout', 'id-user', '2026-01-02', '', '2026-01-02T00:00:00+00:00', 'active', 1)"))
            db.execute(text("INSERT INTO workout_exercises (id, workout_id, exercise_id, position, name_snapshot, weight_mode, weight_scope) VALUES ('we1', 'id-workout', 'bench-press', 0, '卧推', 'external', 'total')"))
            db.execute(text("INSERT INTO workout_sets (id, workout_exercise_id, position, kind, weight_grams, reps, notes) VALUES ('ws1', 'we1', 0, 'working', 60000, 8, '')"))
            db.execute(text("INSERT INTO conversations (id, user_id, title, created_at) VALUES ('id-conversation', 'id-user', '旧对话', '2026-01-01T00:00:00+00:00')"))
            db.execute(text("INSERT INTO workout_drafts (id, user_id, content, version, status, conversation_id) VALUES ('id-draft', 'id-user', '{}', 1, 'editable', 'id-conversation')"))
            db.execute(text("INSERT INTO turns (id, user_id, conversation_id, status, token, deadline, context, created_at) VALUES ('id-turn', 'id-user', 'id-conversation', 'failed', 't', 1, '{}', '2026-01-01T00:00:00+00:00')"))
            db.execute(text("INSERT INTO messages (id, conversation_id, turn_id, role, text, draft_id, created_at) VALUES ('id-message', 'id-conversation', 'id-turn', 'user', '旧消息', 'id-draft', '2026-01-01T00:00:00+00:00')"))
            db.execute(text("INSERT INTO conversation_actions (id, user_id, conversation_id, turn_id, kind, payload, status, version) VALUES ('id-action', 'id-user', 'id-conversation', 'id-turn', 'profile', '{}', 'pending', 1)"))
            db.execute(text("INSERT INTO request_receipts (user_id, request_id, fingerprint, result) VALUES ('id-user', 'legacy-turn-op', 'f', '{\"turn_id\": \"id-turn\", \"status\": \"succeeded\"}')"))
            db.execute(text("INSERT INTO request_receipts (user_id, request_id, fingerprint, result) VALUES ('id-user', 'workout-op', 'f', '{\"id\": \"id-workout\", \"total\": 1}')"))
        engine.dispose()
    return {'user': user_id, 'workout': workout_id, 'draft': draft_id, 'turn': turn_id}


def test_upgrade_clears_conversations_and_keeps_business_data(tmp_path):
    import os
    path = tmp_path / 'legacy.db'
    ids = seed_old_database(path)
    config = _make_config(path)
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('DATABASE_URL', 'sqlite:///' + path.as_posix())
        _upgrade(config, 'head')
        from app.core.database import make_engine
        from sqlalchemy import select, func
        from sqlalchemy.orm import Session
        from app.models import (User, Conversation, Turn, Message, ConversationAction,
                                Workout, WorkoutExercise, WorkoutSet, WorkoutDraft, RequestReceipt, Exercise)
        engine = make_engine('sqlite:///' + path.as_posix())
        with Session(engine) as db:
            assert db.get(User, ids['user']) is not None
            assert db.get(Workout, ids['workout']) is not None
            assert db.get(WorkoutExercise, 'we1') is not None
            assert db.get(WorkoutSet, 'ws1') is not None
            draft = db.get(WorkoutDraft, ids['draft'])
            assert draft is not None and draft.conversation_id is None
            assert db.scalar(select(func.count()).select_from(Exercise)) > 0
            for model in (Conversation, Turn, Message, ConversationAction):
                assert db.scalar(select(func.count()).select_from(model)) == 0
            assert db.get(RequestReceipt, (ids['user'], 'legacy-turn-op')) is None
            kept = db.get(RequestReceipt, (ids['user'], 'workout-op'))
            assert kept is not None and kept.result['id'] == ids['workout']
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
