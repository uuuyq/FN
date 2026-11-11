"""Persist conversations, execution leases, and reviewed actions."""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = depends_on = None


def upgrade():
    op.create_table('conversations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_index('ix_conversations_user_id', 'conversations', ['user_id'])
    # SQLite ADD COLUMN supports a nullable foreign key without rebuilding data.
    op.execute('ALTER TABLE workout_drafts ADD COLUMN conversation_id VARCHAR REFERENCES conversations(id)')
    op.create_index('ix_workout_drafts_conversation_id', 'workout_drafts', ['conversation_id'])
    op.create_table('turns',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('deadline', sa.Integer(), nullable=False),
        sa.Column('context', sa.JSON(), nullable=False),
        sa.Column('error', sa.String()), sa.Column('result', sa.JSON()),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.CheckConstraint("status IN ('running','succeeded','failed','conflict','interrupted')"))
    op.create_index('ix_turns_user_id', 'turns', ['user_id'])
    op.create_index('ix_turns_conversation_id', 'turns', ['conversation_id'])
    op.create_index('uq_running_conversation', 'turns', ['conversation_id'], unique=True, sqlite_where=sa.text("status = 'running'"))
    op.create_table('messages',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('turn_id', sa.String(), sa.ForeignKey('turns.id'), nullable=False),
        sa.Column('role', sa.String(), nullable=False), sa.Column('text', sa.String(), nullable=False),
        sa.Column('draft_id', sa.String(), sa.ForeignKey('workout_drafts.id')),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('turn_id', 'role'), sa.CheckConstraint("role IN ('user','assistant')"))
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_turn_id', 'messages', ['turn_id'])
    op.create_table('conversation_actions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('turn_id', sa.String(), sa.ForeignKey('turns.id'), nullable=False, unique=True),
        sa.Column('kind', sa.String(), nullable=False), sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False), sa.Column('version', sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('pending','confirmed','cancelled')"),
        sa.CheckConstraint("kind IN ('profile','availability','equipment')"))
    op.create_index('ix_conversation_actions_user_id', 'conversation_actions', ['user_id'])


def downgrade():
    for table in ['conversation_actions', 'messages', 'turns']:
        op.drop_table(table)
    op.drop_index('ix_workout_drafts_conversation_id', table_name='workout_drafts')
    op.execute('ALTER TABLE workout_drafts DROP COLUMN conversation_id')
    op.drop_table('conversations')
