"""Tool-calling agent history and confirmation actions.

Development-stage migration: conversations, turns, messages and actions are
cleared (user-approved). Accounts, workouts, catalog, preferences, drafts and
AI configuration are preserved.
"""
import json

from alembic import op
import sqlalchemy as sa

revision = '0010'
down_revision = '0009'
branch_labels = depends_on = None


def _referenced_strings(value, found):
    if isinstance(value, str):
        found.add(value)
    elif isinstance(value, dict):
        for item in value.values():
            _referenced_strings(item, found)
    elif isinstance(value, list):
        for item in value:
            _referenced_strings(item, found)


def upgrade():
    bind = op.get_bind()
    # Collect legacy ids first; receipts referencing them would 404 or conflict.
    deleted = set()
    for table in ('conversations', 'turns', 'conversation_actions'):
        deleted.update(row[0] for row in bind.exec_driver_sql(f'SELECT id FROM {table}'))
    # Foreign-key order: messages -> conversation_actions -> turns -> conversations.
    op.execute('DELETE FROM messages')
    op.execute('DELETE FROM conversation_actions')
    op.execute('DELETE FROM turns')
    op.execute('DELETE FROM conversations')
    op.execute('UPDATE workout_drafts SET conversation_id = NULL')
    stale = []
    for user_id, request_id, raw in bind.exec_driver_sql('SELECT user_id, request_id, result FROM request_receipts'):
        found = set()
        _referenced_strings(json.loads(raw), found)
        if found & deleted:
            stale.append((user_id, request_id))
    for user_id, request_id in stale:
        bind.execute(sa.text('DELETE FROM request_receipts WHERE user_id = :user_id AND request_id = :request_id'),
                     {'user_id': user_id, 'request_id': request_id})

    op.drop_table('conversation_actions')
    op.drop_table('messages')
    op.create_table('messages',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('turn_id', sa.String(), sa.ForeignKey('turns.id'), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('tool_call_id', sa.String(), nullable=True),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('event_kind', sa.String(), nullable=True),
        sa.Column('event_data', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant','tool','event')"))
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_turn_id', 'messages', ['turn_id'])
    op.create_table('conversation_actions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('turn_id', sa.String(), sa.ForeignKey('turns.id'), nullable=False),
        sa.Column('operation', sa.String(), nullable=False),
        sa.Column('tool_name', sa.String(), nullable=False),
        sa.Column('tool_contract_version', sa.String(), nullable=False, server_default='1'),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('completed_at', sa.String(), nullable=True),
        sa.CheckConstraint("status IN ('pending','confirmed','cancelled','superseded','conflict','failed')"))
    op.create_index('ix_conversation_actions_user_id', 'conversation_actions', ['user_id'])


def downgrade():
    op.drop_table('conversation_actions')
    op.drop_table('messages')
    op.create_table('messages',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('turn_id', sa.String(), sa.ForeignKey('turns.id'), nullable=False),
        sa.Column('role', sa.String(), nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('draft_id', sa.String(), sa.ForeignKey('workout_drafts.id'), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('turn_id', 'role'),
        sa.CheckConstraint("role IN ('user','assistant')"))
    op.create_index('ix_messages_conversation_id', 'messages', ['conversation_id'])
    op.create_index('ix_messages_turn_id', 'messages', ['turn_id'])
    op.create_table('conversation_actions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('user_id', sa.String(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=False),
        sa.Column('turn_id', sa.String(), sa.ForeignKey('turns.id'), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.CheckConstraint("status IN ('pending','confirmed','cancelled')"),
        sa.CheckConstraint("kind IN ('profile','availability','equipment','delete_workout')"))
    op.create_index('ix_conversation_actions_user_id', 'conversation_actions', ['user_id'])
