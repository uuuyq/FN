"""Retain closed workouts for seven days."""
from alembic import op
import sqlalchemy as sa
revision = '0009'
down_revision = '0008'
branch_labels = depends_on = None


def upgrade():
    op.add_column('workouts', sa.Column('status', sa.String(), nullable=False, server_default='active'))
    op.execute("UPDATE workouts SET status='closed' WHERE deleted_at IS NOT NULL")
    op.execute("CREATE TRIGGER workouts_status_insert BEFORE INSERT ON workouts WHEN NEW.status NOT IN ('active','closed') BEGIN SELECT RAISE(ABORT, 'invalid workout status'); END")
    op.execute("CREATE TRIGGER workouts_status_update BEFORE UPDATE OF status ON workouts WHEN NEW.status NOT IN ('active','closed') BEGIN SELECT RAISE(ABORT, 'invalid workout status'); END")
    op.create_index('ix_workouts_retention', 'workouts', ['status', 'deleted_at'])


def downgrade():
    op.drop_index('ix_workouts_retention', table_name='workouts')
    op.execute('DROP TRIGGER workouts_status_insert')
    op.execute('DROP TRIGGER workouts_status_update')
    op.drop_column('workouts', 'status')
