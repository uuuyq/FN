"""Agent workout undo history."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
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


def downgrade():
    op.drop_table('agent_operations')
