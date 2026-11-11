"""Remove plans and execution tracking, preserving actual workouts and accounts.

This data removal is irreversible; restore a pre-upgrade backup to recover plans.
Historical revisions remain so existing databases can upgrade normally.
"""
import json

from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = '0007'
branch_labels = depends_on = None

PLAN_KEYS = {'current_plan', 'recent_plans', 'latest_plan_draft', 'pending_execution',
             'plan_draft_id', 'plans', 'execution', 'association', 'selected_for_plan',
             'draft_type', 'auto_route'}


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in PLAN_KEYS}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def upgrade():
    db = op.get_bind()
    # Remove dependent tables before removing message references.
    for table in ('exercise_substitutions', 'task_execution_events', 'workout_task_associations'):
        op.drop_table(table)
    # Delete plan-only turns and attachments; preserve workout turns in mixed chats.
    plan_turns = set(db.execute(sa.text('SELECT turn_id FROM messages WHERE plan_draft_id IS NOT NULL AND draft_id IS NULL')).scalars())
    rows = db.execute(sa.text('SELECT id, context, result FROM turns')).all()
    for turn_id, context, result in rows:
        context = json.loads(context) if isinstance(context, str) else context
        result = json.loads(result) if isinstance(result, str) else result
        if (context or {}).get('draft_type') == 'plan' or (context or {}).get('latest_plan_draft') or 'plans' in (result or {}):
            plan_turns.add(turn_id)
        else:
            db.execute(sa.text('UPDATE turns SET context=:context, result=:result WHERE id=:id'),
                       {'id': turn_id, 'context': json.dumps(clean(context)),
                        'result': json.dumps(clean(result)) if result is not None else None})
    for turn_id in plan_turns:
        db.execute(sa.text('DELETE FROM conversation_actions WHERE turn_id=:id'), {'id': turn_id})
        db.execute(sa.text('DELETE FROM messages WHERE turn_id=:id'), {'id': turn_id})
        db.execute(sa.text('DELETE FROM turns WHERE id=:id'), {'id': turn_id})
    op.drop_column('messages', 'plan_draft_id')
    op.drop_column('workout_drafts', 'association')
    for table in ('plan_exercises', 'training_tasks', 'plan_drafts', 'training_plans'):
        op.drop_table(table)
    op.drop_column('exercise_preferences', 'selected_for_plan')
    # Recreate users to remove the unnamed CHECK involving plan_rounds.
    metadata = sa.MetaData()
    users = sa.Table('users', metadata, autoload_with=db)
    for constraint in list(users.constraints):
        if isinstance(constraint, sa.CheckConstraint) and 'plan_rounds' in str(constraint.sqltext):
            users.constraints.remove(constraint)
    with op.batch_alter_table('users', copy_from=users, recreate='always') as batch:
        batch.drop_column('plan_rounds')
        batch.drop_column('settings_version')
    # Old receipts can contain retired payloads; they must never replay obsolete results.
    db.execute(sa.text('DELETE FROM request_receipts'))


def downgrade():
    raise RuntimeError('Plan removal is irreversible. Restore a pre-upgrade database backup.')
