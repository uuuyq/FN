"""Allow conversation deletion while preserving training audit references."""
from alembic import op
import sqlalchemy as sa
revision = '0006'
down_revision = '0005'
branch_labels = depends_on = None

def upgrade():
    op.add_column('conversations', sa.Column('deleted_at', sa.String(), nullable=True))

def downgrade():
    op.drop_column('conversations', 'deleted_at')
