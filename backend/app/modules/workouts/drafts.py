"""Shared draft operations. Caller owns the short write transaction.

Used by the manual training editor. Agent confirmations use their own actions
and share only the workout domain services; no model calls belong here.
"""
from ...models import WorkoutDraft, Workout
from ...schemas import WorkoutContent
from ...services import fail, owned, version, serialize
from .service import normalized_content, workout_view, editable_content, save_workout

def create_draft(db, user_id, body):
    original = owned(db, Workout, body.original_id, user_id) if body.original_id else None
    if original and original.deleted_at:
        fail(409, 'workout_trashed')
    content = editable_content(workout_view(db, original)) if original else body.content
    row = WorkoutDraft(user_id=user_id, content=normalized_content(db, user_id, content), original_id=original.id if original else None, original_version=original.version if original else None)
    db.add(row)
    db.flush()
    return serialize(row)


def update_draft(db, user_id, object_id, body):
    row = owned(db, WorkoutDraft, object_id, user_id)
    version(row, body.version)
    if row.status != 'editable':
        fail(409, 'draft_not_editable')
    row.content = normalized_content(db, user_id, body.content)
    row.version += 1
    return serialize(row)


def finalize_draft(db, user_id, object_id, operation, body):
    row = owned(db, WorkoutDraft, object_id, user_id)
    if operation == 'confirm' and row.status == 'confirmed':
        return workout_view(db, owned(db, Workout, row.result_id, user_id))
    if operation == 'cancel' and row.status == 'cancelled':
        return serialize(row)
    version(row, body.version)
    if row.status != 'editable':
        fail(409, 'draft_not_editable')
    if operation == 'cancel':
        row.status, row.version = 'cancelled', row.version + 1
        return serialize(row)
    original = owned(db, Workout, row.original_id, user_id) if row.original_id else None
    if original:
        version(original, row.original_version)
        if original.deleted_at:
            fail(409, 'workout_trashed')
    workout = save_workout(db, user_id, normalized_content(db, user_id, WorkoutContent.model_validate(row.content)), original)
    row = db.get(WorkoutDraft, object_id)
    row.status, row.result_id, row.version = 'confirmed', workout.id, row.version + 1
    return workout_view(db, workout)
