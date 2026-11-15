"""Initial FitPlan schema with public/user catalogs and two-level training records."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('equipment',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('public_exercises',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('normalized_name', sa.String(length=100), nullable=False),
    sa.Column('aliases', sa.Text(), nullable=False),
    sa.Column('search_text', sa.Text(), nullable=False),
    sa.Column('primary_muscles', sa.Text(), nullable=False),
    sa.Column('secondary_muscles', sa.Text(), nullable=False),
    sa.Column('equipment', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('normalized_name')
    )
    op.create_index('ix_public_exercises_name_id', 'public_exercises', ['name', 'id'], unique=False)
    op.create_table('users',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('username', sa.String(length=100), nullable=False),
    sa.Column('password_hash', sa.String(), nullable=False),
    sa.Column('profile', sa.JSON(), nullable=False),
    sa.Column('profile_version', sa.Integer(), nullable=False),
    sa.Column('ai_config', sa.JSON(), nullable=True),
    sa.Column('ai_config_version', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('conversations',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('deleted_at', sa.String(), nullable=True),
    sa.Column('title', sa.String(), nullable=False),
    sa.Column('created_at', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversations_user_id'), 'conversations', ['user_id'], unique=False)
    op.create_table('request_receipts',
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('request_id', sa.String(), nullable=False),
    sa.Column('fingerprint', sa.String(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'request_id')
    )
    op.create_table('user_equipment',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('equipment_id', sa.String(), nullable=True),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['equipment_id'], ['equipment.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_equipment_user_id'), 'user_equipment', ['user_id'], unique=False)
    op.create_table('user_exercises',
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('normalized_name', sa.String(length=100), nullable=False),
    sa.Column('aliases', sa.Text(), nullable=False),
    sa.Column('search_text', sa.Text(), nullable=False),
    sa.Column('primary_muscles', sa.Text(), nullable=False),
    sa.Column('secondary_muscles', sa.Text(), nullable=False),
    sa.Column('equipment', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'normalized_name')
    )
    op.create_index('ix_user_exercises_user_name_id', 'user_exercises', ['user_id', 'name', 'id'], unique=False)
    op.create_table('user_sessions',
    sa.Column('token_hash', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('csrf', sa.String(), nullable=False),
    sa.Column('expires', sa.Integer(), nullable=False),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('token_hash')
    )
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_table('workouts',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('actual_date', sa.String(), nullable=False),
    sa.Column('actual_time', sa.String(), nullable=True),
    sa.Column('notes', sa.String(), nullable=False),
    sa.Column('created_at', sa.String(), nullable=False),
    sa.Column('deleted_at', sa.String(), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_workouts_retention', 'workouts', ['deleted_at'], unique=False)
    op.create_index('ix_workouts_user_date', 'workouts', ['user_id', 'actual_date'], unique=False)
    op.create_index(op.f('ix_workouts_user_id'), 'workouts', ['user_id'], unique=False)
    op.create_table('turns',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('conversation_id', sa.String(), nullable=False),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('token', sa.String(), nullable=False),
    sa.Column('deadline', sa.Integer(), nullable=False),
    sa.Column('context', sa.JSON(), nullable=False),
    sa.Column('error', sa.String(), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.String(), nullable=False),
    sa.CheckConstraint("status IN ('running','succeeded','failed','conflict','interrupted')"),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_turns_conversation_id'), 'turns', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_turns_user_id'), 'turns', ['user_id'], unique=False)
    op.create_index('uq_running_conversation', 'turns', ['conversation_id'], unique=True, sqlite_where=sa.text("status = 'running'"))
    op.create_table('user_exercise_preferences',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('public_exercise_id', sa.String(), nullable=True),
    sa.Column('user_exercise_id', sa.String(), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.CheckConstraint('(public_exercise_id IS NOT NULL AND user_exercise_id IS NULL) OR (public_exercise_id IS NULL AND user_exercise_id IS NOT NULL)', name='ck_preference_target'),
    sa.ForeignKeyConstraint(['public_exercise_id'], ['public_exercises.id'], ),
    sa.ForeignKeyConstraint(['user_exercise_id'], ['user_exercises.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'public_exercise_id'),
    sa.UniqueConstraint('user_id', 'user_exercise_id')
    )
    op.create_index('ix_user_exercise_preferences_user_active', 'user_exercise_preferences', ['user_id', 'active'], unique=False)
    op.create_table('workout_sets',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('workout_id', sa.String(), nullable=False),
    sa.Column('public_exercise_id', sa.String(), nullable=True),
    sa.Column('user_exercise_id', sa.String(), nullable=True),
    sa.Column('exercise_position', sa.Integer(), nullable=False),
    sa.Column('set_position', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(), nullable=False),
    sa.Column('weight_grams', sa.Integer(), nullable=True),
    sa.Column('reps', sa.Integer(), nullable=True),
    sa.Column('notes', sa.String(), nullable=False),
    sa.CheckConstraint("kind IN ('working','warmup')"),
    sa.CheckConstraint('(public_exercise_id IS NOT NULL AND user_exercise_id IS NULL) OR (public_exercise_id IS NULL AND user_exercise_id IS NOT NULL)', name='ck_workout_set_target'),
    sa.CheckConstraint('exercise_position >= 0 AND set_position >= 0'),
    sa.CheckConstraint('reps IS NULL OR reps >= 0'),
    sa.CheckConstraint('weight_grams IS NULL OR weight_grams >= 0'),
    sa.ForeignKeyConstraint(['public_exercise_id'], ['public_exercises.id'], ),
    sa.ForeignKeyConstraint(['user_exercise_id'], ['user_exercises.id'], ),
    sa.ForeignKeyConstraint(['workout_id'], ['workouts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('workout_id', 'exercise_position', 'set_position')
    )
    op.create_index(op.f('ix_workout_sets_workout_id'), 'workout_sets', ['workout_id'], unique=False)
    op.create_table('conversation_actions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('user_id', sa.String(), nullable=False),
    sa.Column('conversation_id', sa.String(), nullable=False),
    sa.Column('turn_id', sa.String(), nullable=False),
    sa.Column('operation', sa.String(), nullable=False),
    sa.Column('tool_name', sa.String(), nullable=False),
    sa.Column('tool_contract_version', sa.String(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=False),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('status', sa.String(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.String(), nullable=False),
    sa.Column('completed_at', sa.String(), nullable=True),
    sa.CheckConstraint("status IN ('pending','confirmed','cancelled','superseded','conflict','failed')"),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.ForeignKeyConstraint(['turn_id'], ['turns.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_conversation_actions_user_id'), 'conversation_actions', ['user_id'], unique=False)
    op.create_table('messages',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('conversation_id', sa.String(), nullable=False),
    sa.Column('turn_id', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('tool_calls', sa.JSON(), nullable=True),
    sa.Column('tool_call_id', sa.String(), nullable=True),
    sa.Column('sequence', sa.Integer(), nullable=False),
    sa.Column('event_kind', sa.String(), nullable=True),
    sa.Column('event_data', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.String(), nullable=False),
    sa.CheckConstraint("role IN ('user','assistant','tool','event')"),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.ForeignKeyConstraint(['turn_id'], ['turns.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_messages_conversation_id'), 'messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_messages_turn_id'), 'messages', ['turn_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_messages_turn_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_conversation_id'), table_name='messages')
    op.drop_table('messages')
    op.drop_index(op.f('ix_conversation_actions_user_id'), table_name='conversation_actions')
    op.drop_table('conversation_actions')
    op.drop_index(op.f('ix_workout_sets_workout_id'), table_name='workout_sets')
    op.drop_table('workout_sets')
    op.drop_index('ix_user_exercise_preferences_user_active', table_name='user_exercise_preferences')
    op.drop_table('user_exercise_preferences')
    op.drop_index('uq_running_conversation', table_name='turns', sqlite_where=sa.text("status = 'running'"))
    op.drop_index(op.f('ix_turns_user_id'), table_name='turns')
    op.drop_index(op.f('ix_turns_conversation_id'), table_name='turns')
    op.drop_table('turns')
    op.drop_index(op.f('ix_workouts_user_id'), table_name='workouts')
    op.drop_index('ix_workouts_user_date', table_name='workouts')
    op.drop_index('ix_workouts_retention', table_name='workouts')
    op.drop_table('workouts')
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_table('user_sessions')
    op.drop_index('ix_user_exercises_user_name_id', table_name='user_exercises')
    op.drop_table('user_exercises')
    op.drop_index(op.f('ix_user_equipment_user_id'), table_name='user_equipment')
    op.drop_table('user_equipment')
    op.drop_table('request_receipts')
    op.drop_index(op.f('ix_conversations_user_id'), table_name='conversations')
    op.drop_table('conversations')
    op.drop_table('users')
    op.drop_index('ix_public_exercises_name_id', table_name='public_exercises')
    op.drop_table('public_exercises')
    op.drop_table('equipment')
