"""Atomic undo history for successful Agent workout writes."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from ..models import AgentOperation, Workout, now
from ..services import owned, fail
from ..schemas import WorkoutContent
from ..modules.workouts.service import workout_view, normalized_content, save_workout, delete_workout


def capture_before(ctx, action):
    if action.operation in ('update_workout', 'delete_workout'):
        content = workout_view(ctx.db, owned(ctx.db, Workout, action.payload['workout_id'], ctx.user_id))['content']
        for item in content['exercises']:
            item.pop('name', None)
        return content
    return None


def record_operation(ctx, action, before, receipt):
    if action.operation == 'undo_operation':
        row = owned(ctx.db, AgentOperation, action.payload['operation_id'], ctx.user_id)
        row.undo_action_id = action.id
        row.undo_result = dict(receipt)
        return
    if action.operation not in ('create_workout', 'update_workout', 'delete_workout'):
        return
    workout_id = receipt.get('workout_id') or receipt['id']
    workout = ctx.db.get(Workout, workout_id)
    row = AgentOperation(user_id=ctx.user_id, workout_id=workout_id, action_id=action.id,
        operation=action.operation, summary=action.summary, before=before, after_version=workout.version)
    ctx.db.add(row)
    ctx.db.flush()
    receipt['operation_id'] = row.id


def undo_reason(db, row):
    if row.undone_at:
        return 'operation_already_undone'
    if datetime.fromisoformat(row.created_at) <= datetime.now(timezone.utc) - timedelta(days=7):
        return 'operation_expired'
    workout = db.get(Workout, row.workout_id)
    if workout is None or workout.user_id != row.user_id:
        return 'not_found'
    if workout.version != row.after_version:
        return 'version_conflict'
    if row.operation != 'create_workout' and row.before is None:
        return 'snapshot_missing'
    if row.before:
        from ..modules.workouts.service import validate_exercise_references
        from fastapi import HTTPException
        try:
            validate_exercise_references(db, row.user_id, row.before)
        except HTTPException:
            return 'exercise_not_found'
    return None


def undo_target(ctx, operation_id):
    row = owned(ctx.db, AgentOperation, operation_id, ctx.user_id)
    reason = undo_reason(ctx.db, row)
    if reason:
        fail(409, reason)
    return row


def execute_undo(ctx, params):
    row = undo_target(ctx, params.operation_id)
    workout = ctx.db.get(Workout, row.workout_id)
    if row.operation == 'create_workout':
        delete_workout(ctx.db, ctx.user_id, workout.id, row.after_version)
    else:
        data = normalized_content(ctx.db, ctx.user_id, WorkoutContent.model_validate(row.before))
        save_workout(ctx.db, ctx.user_id, data, workout)
        workout.deleted_at = None
    row.undone_at = now()
    ctx.db.flush()
    return {'operation_id': row.id, 'workout_id': workout.id, 'version': workout.version,
            'summary': '已撤销：' + row.summary}


def list_operations(ctx, params):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    stmt = select(AgentOperation).where(AgentOperation.user_id == ctx.user_id, AgentOperation.created_at > cutoff)
    if params.workout_id:
        stmt = stmt.where(AgentOperation.workout_id == params.workout_id)
    total = ctx.db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = ctx.db.scalars(stmt.order_by(AgentOperation.created_at.desc(), AgentOperation.id.desc()).offset(params.offset).limit(params.limit)).all()
    items = []
    for row in rows:
        reason = undo_reason(ctx.db, row)
        items.append({'operation_id': row.id, 'operation': row.operation, 'workout_id': row.workout_id,
            'summary': row.summary, 'created_at': row.created_at, 'undone': bool(row.undone_at),
            'can_undo': reason is None, 'reason': reason})
    next_offset = params.offset + len(items)
    return {'items': items, 'total': total, 'has_more': next_offset < total,
            'next_offset': next_offset if next_offset < total else None}
