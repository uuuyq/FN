from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String, Text, UniqueConstraint, Index, text
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


class Exercise(Base):
    __tablename__ = 'exercises'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    muscles: Mapped[list] = mapped_column(JSON, default=list)
    secondary_muscles: Mapped[list] = mapped_column(JSON, default=list)
    equipment: Mapped[list] = mapped_column(JSON, default=list)
    archived: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(default=1)


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


class ExercisePreference(Base):
    __tablename__ = 'exercise_preferences'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), primary_key=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey('exercises.id'), primary_key=True)
    available: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(default=1)


class WorkoutDraft(Base):
    __tablename__ = 'workout_drafts'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    content: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(default='editable')
    original_id: Mapped[str | None] = mapped_column(ForeignKey('workouts.id'))
    original_version: Mapped[int | None]
    result_id: Mapped[str | None] = mapped_column(ForeignKey('workouts.id'))
    conversation_id: Mapped[str | None] = mapped_column(ForeignKey('conversations.id'), index=True)
    __table_args__ = (CheckConstraint("status IN ('editable','confirmed','cancelled')"),)


class Workout(Base):
    __tablename__ = 'workouts'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True)
    actual_date: Mapped[str] = mapped_column(index=True)
    actual_time: Mapped[str | None]
    notes: Mapped[str] = mapped_column(default='')
    created_at: Mapped[str] = mapped_column(default=now)
    status: Mapped[str] = mapped_column(default='active', server_default='active')
    deleted_at: Mapped[str | None]
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (CheckConstraint("status IN ('active','closed')"), Index('ix_workouts_retention', 'status', 'deleted_at'))


class WorkoutExercise(Base):
    __tablename__ = 'workout_exercises'
    id: Mapped[str] = mapped_column(primary_key=True)
    workout_id: Mapped[str] = mapped_column(ForeignKey('workouts.id'), index=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey('exercises.id'))
    position: Mapped[int]
    name_snapshot: Mapped[str]
    weight_mode: Mapped[str]
    weight_scope: Mapped[str]
    __table_args__ = (UniqueConstraint('workout_id', 'position'), CheckConstraint('position >= 0'), CheckConstraint("weight_mode IN ('external','bodyweight','added','assisted','unknown')"), CheckConstraint("weight_scope IN ('total','per_side','unknown')"))


class WorkoutSet(Base):
    __tablename__ = 'workout_sets'
    id: Mapped[str] = mapped_column(primary_key=True)
    workout_exercise_id: Mapped[str] = mapped_column(ForeignKey('workout_exercises.id'), index=True)
    position: Mapped[int]
    kind: Mapped[str]
    weight_grams: Mapped[int | None]
    reps: Mapped[int | None]
    notes: Mapped[str]
    __table_args__ = (UniqueConstraint('workout_exercise_id', 'position'), CheckConstraint('position >= 0'), CheckConstraint("kind IN ('working','warmup')"), CheckConstraint('weight_grams IS NULL OR weight_grams >= 0'), CheckConstraint('reps IS NULL OR reps >= 0'))


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
