from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text, UniqueConstraint, Index, text, event
from sqlalchemy.orm import Mapped, mapped_column

from .core.database import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc).isoformat()


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str]
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    profile_version: Mapped[int] = mapped_column(default=1)
    ai_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_config_version: Mapped[int] = mapped_column(default=1)


class UserSession(Base):
    __tablename__ = 'user_sessions'
    token_hash: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    csrf: Mapped[str]
    expires: Mapped[int]
    revoked: Mapped[bool] = mapped_column(default=False)


class ExerciseFields:
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(100))
    normalized_name: Mapped[str] = mapped_column(String(100))
    aliases: Mapped[str] = mapped_column(Text, default='')
    search_text: Mapped[str] = mapped_column(Text, default='')
    primary_muscles: Mapped[str] = mapped_column(Text, default='')
    secondary_muscles: Mapped[str] = mapped_column(Text, default='')
    equipment: Mapped[str] = mapped_column(Text, default='')
    description: Mapped[str] = mapped_column(Text, default='')
    version: Mapped[int] = mapped_column(default=1)


class PublicExercise(ExerciseFields, Base):
    __tablename__ = 'public_exercises'
    __table_args__ = (UniqueConstraint('normalized_name'),
                      Index('ix_public_exercises_name_id', 'name', 'id'))

    @property
    def owner_id(self):
        return None


class UserExercise(ExerciseFields, Base):
    __tablename__ = 'user_exercises'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    __table_args__ = (UniqueConstraint('user_id', 'normalized_name'),
                      Index('ix_user_exercises_user_name_id', 'user_id', 'name', 'id'))

    @property
    def owner_id(self):
        return self.user_id


def normalize_exercise_text(value):
    import unicodedata
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


@event.listens_for(PublicExercise, 'before_insert')
@event.listens_for(PublicExercise, 'before_update')
@event.listens_for(UserExercise, 'before_insert')
@event.listens_for(UserExercise, 'before_update')
def normalize_exercise_fields(mapper, connection, target):
    target.name = target.name.strip()
    target.normalized_name = normalize_exercise_text(target.name)
    target.search_text = normalize_exercise_text(target.name + ' ' + (target.aliases or ''))


class Equipment(Base):
    __tablename__ = 'equipment'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(unique=True)


class UserEquipment(Base):
    __tablename__ = 'user_equipment'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    equipment_id: Mapped[str | None] = mapped_column(ForeignKey('equipment.id'))
    name: Mapped[str]
    version: Mapped[int] = mapped_column(default=1)


class UserExercisePreference(Base):
    __tablename__ = 'user_exercise_preferences'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    public_exercise_id: Mapped[str | None] = mapped_column(ForeignKey('public_exercises.id'))
    user_exercise_id: Mapped[str | None] = mapped_column(ForeignKey('user_exercises.id'))
    active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        CheckConstraint('(public_exercise_id IS NOT NULL AND user_exercise_id IS NULL) OR '
                        '(public_exercise_id IS NULL AND user_exercise_id IS NOT NULL)', name='ck_preference_target'),
        UniqueConstraint('user_id', 'public_exercise_id'),
        UniqueConstraint('user_id', 'user_exercise_id'),
        Index('ix_user_exercise_preferences_user_active', 'user_id', 'active'),
    )


class Workout(Base):
    __tablename__ = 'workouts'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    actual_date: Mapped[str]
    actual_time: Mapped[str | None]
    notes: Mapped[str] = mapped_column(default='')
    created_at: Mapped[str] = mapped_column(default=now)
    deleted_at: Mapped[str | None]
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (Index('ix_workouts_user_date', 'user_id', 'actual_date'),
                      Index('ix_workouts_retention', 'deleted_at'))


class WorkoutSet(Base):
    __tablename__ = 'workout_sets'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    workout_id: Mapped[str] = mapped_column(ForeignKey('workouts.id', ondelete='CASCADE'), index=True)
    public_exercise_id: Mapped[str | None] = mapped_column(ForeignKey('public_exercises.id'))
    user_exercise_id: Mapped[str | None] = mapped_column(ForeignKey('user_exercises.id'))
    exercise_position: Mapped[int]
    set_position: Mapped[int]
    kind: Mapped[str]
    weight_grams: Mapped[int | None]
    reps: Mapped[int | None]
    notes: Mapped[str]
    __table_args__ = (
        CheckConstraint('(public_exercise_id IS NOT NULL AND user_exercise_id IS NULL) OR '
                        '(public_exercise_id IS NULL AND user_exercise_id IS NOT NULL)', name='ck_workout_set_target'),
        UniqueConstraint('workout_id', 'exercise_position', 'set_position'),
        CheckConstraint('exercise_position >= 0 AND set_position >= 0'),
        CheckConstraint("kind IN ('working','warmup')"),
        CheckConstraint('weight_grams IS NULL OR weight_grams >= 0'),
        CheckConstraint('reps IS NULL OR reps >= 0'),
    )


class RequestReceipt(Base):
    __tablename__ = 'request_receipts'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    request_id: Mapped[str] = mapped_column(primary_key=True)
    fingerprint: Mapped[str]
    result: Mapped[dict] = mapped_column(JSON)


class Conversation(Base):
    __tablename__ = 'conversations'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    deleted_at: Mapped[str | None]
    title: Mapped[str]
    created_at: Mapped[str] = mapped_column(default=now)


class Turn(Base):
    __tablename__ = 'turns'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), index=True)
    status: Mapped[str] = mapped_column(default='running')
    token: Mapped[str]
    deadline: Mapped[int]
    context: Mapped[dict] = mapped_column(JSON)
    error: Mapped[str | None]
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (CheckConstraint("status IN ('running','succeeded','failed','conflict','interrupted')"),
        Index('uq_running_conversation', 'conversation_id', unique=True, sqlite_where=text("status = 'running'")))


class Message(Base):
    __tablename__ = 'messages'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'), index=True)
    turn_id: Mapped[str] = mapped_column(ForeignKey('turns.id'), index=True)
    role: Mapped[str]
    content: Mapped[str] = mapped_column(Text, default='')
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    tool_call_id: Mapped[str | None]
    sequence: Mapped[int]
    event_kind: Mapped[str | None]
    event_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(default=now)
    __table_args__ = (CheckConstraint("role IN ('user','assistant','tool','event')"),)


class ConversationAction(Base):
    __tablename__ = 'conversation_actions'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id'))
    turn_id: Mapped[str] = mapped_column(ForeignKey('turns.id'))
    operation: Mapped[str]
    tool_name: Mapped[str]
    tool_contract_version: Mapped[str] = mapped_column(default='1')
    payload: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(default='pending')
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[str] = mapped_column(default=now)
    completed_at: Mapped[str | None]
    __table_args__ = (CheckConstraint("status IN ('pending','confirmed','cancelled','superseded','conflict','failed')"),)


class AgentOperation(Base):
    __tablename__ = 'agent_operations'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    workout_id: Mapped[str]
    action_id: Mapped[str] = mapped_column(ForeignKey('conversation_actions.id'), unique=True)
    operation: Mapped[str]
    summary: Mapped[str] = mapped_column(Text)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_version: Mapped[int]
    created_at: Mapped[str] = mapped_column(default=now, index=True)
    undone_at: Mapped[str | None]
    undo_action_id: Mapped[str | None]
    undo_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
