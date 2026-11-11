"""Per-user AI model connection configuration."""
from alembic import op
import sqlalchemy as sa
revision = '0007'
down_revision = '0006'
branch_labels = depends_on = None

def upgrade():
    op.add_column('users', sa.Column('ai_config', sa.JSON(), nullable=True))
    op.add_column('users', sa.Column('ai_config_version', sa.Integer(), nullable=False, server_default='1'))

def downgrade():
    op.drop_column('users', 'ai_config_version')
    op.drop_column('users', 'ai_config')
