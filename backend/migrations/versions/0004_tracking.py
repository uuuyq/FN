"""Atomic task execution, explicit association and immutable audit events."""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TABLE workout_drafts ADD COLUMN association JSON NOT NULL DEFAULT '{}'")
    op.create_table('workout_task_associations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('workout_id', sa.String(), sa.ForeignKey('workouts.id'), unique=True, nullable=False),
        sa.Column('task_id', sa.String(), sa.ForeignKey('training_tasks.id'), unique=True),
        sa.Column('decision', sa.String(), nullable=False), sa.Column('source', sa.String(), nullable=False),
        sa.Column('source_message_id', sa.String(), sa.ForeignKey('messages.id')),
        sa.CheckConstraint("decision IN ('none','task')"),
        sa.CheckConstraint("(decision = 'task' AND task_id IS NOT NULL) OR (decision = 'none' AND task_id IS NULL)"))
    op.create_table('exercise_substitutions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('association_id', sa.String(), sa.ForeignKey('workout_task_associations.id'), nullable=False),
        sa.Column('plan_exercise_id', sa.String(), sa.ForeignKey('plan_exercises.id'), nullable=False),
        sa.Column('actual_exercise_id', sa.String(), nullable=False),
        sa.UniqueConstraint('association_id', 'actual_exercise_id'))
    op.create_index('ix_exercise_substitutions_association_id', 'exercise_substitutions', ['association_id'])
    op.create_table('task_execution_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('task_id', sa.String(), sa.ForeignKey('training_tasks.id'), nullable=False),
        sa.Column('workout_id', sa.String(), sa.ForeignKey('workouts.id')),
        sa.Column('kind', sa.String(), nullable=False), sa.Column('source', sa.String(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False), sa.Column('created_at', sa.String(), nullable=False),
        sa.CheckConstraint("kind IN ('execute','skip','makeup','unlink','reassign')"))
    op.create_index('ix_task_execution_events_task_id', 'task_execution_events', ['task_id'])


def downgrade():
    op.drop_table('task_execution_events')
    op.drop_table('exercise_substitutions')
    op.drop_table('workout_task_associations')
    op.execute('ALTER TABLE workout_drafts DROP COLUMN association')
