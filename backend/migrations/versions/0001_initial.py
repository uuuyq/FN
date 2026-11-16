"""Initial FitPlan schema with public/user catalogs and two-level training records."""
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def create_initial_schema():
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


def drop_initial_schema():
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


def upgrade_operations():
    op.create_table('agent_operations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('workout_id', sa.String(), nullable=False),
        sa.Column('action_id', sa.String(), sa.ForeignKey('conversation_actions.id'), nullable=False, unique=True),
        sa.Column('operation', sa.String(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('before', sa.JSON(), nullable=True),
        sa.Column('after_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('undone_at', sa.String(), nullable=True),
        sa.Column('undo_action_id', sa.String(), nullable=True),
        sa.Column('undo_result', sa.JSON(), nullable=True))
    op.create_index('ix_agent_operations_user_id', 'agent_operations', ['user_id'])
    op.create_index('ix_agent_operations_created_at', 'agent_operations', ['created_at'])


def downgrade_operations():
    op.drop_table('agent_operations')


def upgrade_profile():
    db = op.get_bind()
    users = sa.table('users', sa.column('id', sa.String), sa.column('profile', sa.JSON),
                     sa.column('profile_version', sa.Integer))
    for row in db.execute(sa.select(users)).mappings():
        profile = dict(row['profile'] or {})
        parts = [profile.get('preferences', '')]
        for key, label in (('goal', '训练目标'), ('restrictions', '限制')):
            value = profile.pop(key, '')
            if value:
                parts.append(label + '：' + value)
        profile['preferences'] = '\n'.join(part for part in parts if part)
        profile.setdefault('training_principles', '')
        profile.setdefault('history_workout_count', 7)
        db.execute(users.update().where(users.c.id == row['id']).values(
            profile=profile, profile_version=row['profile_version'] + 1))
    actions = sa.table('conversation_actions', sa.column('tool_name', sa.String),
        sa.column('status', sa.String), sa.column('version', sa.Integer),
        sa.column('completed_at', sa.String), sa.column('summary', sa.Text))
    db.execute(actions.update().where(actions.c.tool_name == 'update_profile',
        actions.c.status == 'pending').values(status='superseded', version=actions.c.version + 1,
        completed_at=datetime.now(timezone.utc).isoformat(), summary='个人条件字段已更新，请重新发起修改。'))


def downgrade_profile():
    # Keep user-authored preferences intact when reverting the application.
    pass


def upgrade_categories():
    for table in ('equipment', 'user_equipment'):
        op.add_column(table, sa.Column('category', sa.String(), nullable=False, server_default='其他'))
    db = op.get_bind()
    categories = {'barbell': '自由重量', 'dumbbell': '自由重量', 'kettlebell': '自由重量', 'ez-bar': '自由重量', 'trap-bar': '自由重量', 'plates': '自由重量', 'smith': '固定器械', 'cable': '固定器械', 'lat-pulldown': '固定器械', 'seated-row': '固定器械', 'chest-press': '固定器械', 'pec-deck': '固定器械', 'shoulder-press': '固定器械', 'leg-press': '固定器械', 'hack-squat': '固定器械', 'leg-extension': '固定器械', 'leg-curl': '固定器械', 'hip-thrust': '固定器械', 'hip-abduction': '固定器械', 'hip-adduction': '固定器械', 'calf-raise': '固定器械', 'assisted-pullup': '固定器械', 'bench': '训练架与凳', 'pullup': '训练架与凳', 'rack': '训练架与凳', 'dip-bars': '训练架与凳', 'roman-chair': '训练架与凳', 'preacher-bench': '训练架与凳', 'treadmill': '有氧器械', 'bike': '有氧器械', 'air-bike': '有氧器械', 'rower': '有氧器械', 'elliptical': '有氧器械', 'stair-climber': '有氧器械', 'ski-erg': '有氧器械', 'band': '功能训练', 'mini-band': '功能训练', 'trx': '功能训练', 'gym-rings': '功能训练', 'stability-ball': '功能训练', 'medicine-ball': '功能训练', 'slam-ball': '功能训练', 'bosu': '功能训练', 'ab-wheel': '功能训练', 'box': '功能训练', 'step': '功能训练', 'rope': '功能训练', 'battle-rope': '功能训练', 'sled': '功能训练', 'sandbag': '功能训练', 'mat': '辅助与恢复', 'foam-roller': '辅助与恢复'}
    for equipment_id, category in categories.items():
        db.execute(sa.text('UPDATE equipment SET category = :category WHERE id = :id'), {'category': category, 'id': equipment_id})
    db.execute(sa.text('UPDATE user_equipment SET category = (SELECT category FROM equipment WHERE equipment.id = user_equipment.equipment_id) WHERE equipment_id IS NOT NULL'))


def downgrade_categories():
    op.drop_column('user_equipment', 'category')
    op.drop_column('equipment', 'category')


def upgrade():
    create_initial_schema()
    upgrade_operations()
    upgrade_categories()


def downgrade():
    downgrade_operations()
    drop_initial_schema()
