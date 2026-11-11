"""Allow confirmed workout deletion proposals without changing existing actions."""
from alembic import op
import sqlalchemy as sa
revision = '0005'
down_revision = '0004'
branch_labels = depends_on = None

def change(expression):
    table = sa.Table('conversation_actions', sa.MetaData(), autoload_with=op.get_bind())
    for constraint in table.constraints:
        if isinstance(constraint, sa.CheckConstraint):
            constraint.name = 'action_kind' if 'kind IN' in str(constraint.sqltext) else 'action_status'
    with op.batch_alter_table('conversation_actions', copy_from=table, recreate='always') as batch:
        batch.drop_constraint('action_kind', type_='check')
        batch.create_check_constraint('action_kind', expression)

def upgrade():
    change("kind IN ('profile','availability','equipment','delete_workout')")

def downgrade():
    op.execute("DELETE FROM conversation_actions WHERE kind = 'delete_workout'")
    change("kind IN ('profile','availability','equipment')")
