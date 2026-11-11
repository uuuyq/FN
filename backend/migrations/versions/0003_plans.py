"""Immutable plans and shared plan drafts; preserve existing conversations."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = depends_on = None


def upgrade():
    op.create_table('training_plans',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False), sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False), sa.Column('next_position', sa.Integer(), nullable=False),
        sa.Column('deleted_at', sa.String()), sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('active','ended')"), sa.CheckConstraint('next_position >= 0'))
    op.create_index('ix_training_plans_user_id', 'training_plans', ['user_id'])
    op.create_index('uq_active_plan_user', 'training_plans', ['user_id'], unique=True,
        sqlite_where=sa.text("status = 'active' AND deleted_at IS NULL"))
    op.create_table('plan_drafts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id')),
        sa.Column('snapshot', sa.JSON(), nullable=False), sa.Column('content', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('status', sa.String(), nullable=False),
        sa.Column('result_id', sa.String(), sa.ForeignKey('training_plans.id')),
        sa.CheckConstraint("status IN ('editable','confirmed','cancelled')"))
    op.create_index('ix_plan_drafts_user_id', 'plan_drafts', ['user_id'])
    op.execute('ALTER TABLE messages ADD COLUMN plan_draft_id VARCHAR REFERENCES plan_drafts(id)')
    op.create_table('training_tasks',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('plan_id', sa.String(), sa.ForeignKey('training_plans.id'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False), sa.Column('round', sa.Integer(), nullable=False),
        sa.Column('theme', sa.String(), nullable=False), sa.Column('status', sa.String(), nullable=False),
        sa.UniqueConstraint('plan_id', 'position'), sa.CheckConstraint('position >= 0'),
        sa.CheckConstraint('round > 0'), sa.CheckConstraint("status IN ('pending','executed','skipped')"))
    op.create_index('ix_training_tasks_plan_id', 'training_tasks', ['plan_id'])
    op.create_table('plan_exercises',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('task_id', sa.String(), sa.ForeignKey('training_tasks.id'), nullable=False),
        sa.Column('exercise_id', sa.String(), sa.ForeignKey('exercises.id'), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False), sa.Column('name_snapshot', sa.String(), nullable=False),
        sa.Column('target_sets', sa.Integer(), nullable=False), sa.Column('reps_min', sa.Integer(), nullable=False),
        sa.Column('reps_max', sa.Integer(), nullable=False), sa.UniqueConstraint('task_id', 'position'),
        sa.CheckConstraint('position >= 0'), sa.CheckConstraint('target_sets > 0'),
        sa.CheckConstraint('reps_min > 0 AND reps_max >= reps_min'))
    op.create_index('ix_plan_exercises_task_id', 'plan_exercises', ['task_id'])


def downgrade():
    op.drop_table('plan_exercises')
    op.drop_table('training_tasks')
    op.execute('ALTER TABLE messages DROP COLUMN plan_draft_id')
    op.drop_table('plan_drafts')
    op.drop_table('training_plans')
