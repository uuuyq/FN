"""Workout domain services shared by the HTTP router and the Agent tools."""
from decimal import Decimal

from sqlalchemy import delete, func, select

from ...models import Exercise, Workout, WorkoutExercise, WorkoutSet, uid
from ...schemas import WorkoutContent
from ...services import exercise, fail, owned, version


def query_workouts(db, user_id, *, on=None, start=None, end=None, exercise_id=None, offset=0, limit=50):
    """Owned, stable-ordered listing with SQL pagination. Returns (rows, total)."""
    stmt = select(Workout).where(Workout.user_id == user_id, Workout.status == 'active', Workout.deleted_at.is_(None))
    if on:
        stmt = stmt.where(Workout.actual_date == on.isoformat())
    if start:
        stmt = stmt.where(Workout.actual_date >= start.isoformat())
    if end:
        stmt = stmt.where(Workout.actual_date <= end.isoformat())
    if exercise_id:
        exercise(db, exercise_id, user_id)
        stmt = stmt.where(Workout.id.in_(select(WorkoutExercise.workout_id).where(WorkoutExercise.exercise_id == exercise_id)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Workout.actual_date.desc(), Workout.actual_time.desc(), Workout.created_at.desc(), Workout.id.desc()).offset(offset).limit(limit)).all()
    return rows, total


def normalized_content(db, user_id, content):
    data = content.model_dump(mode='json')
    seen = set()
    for item in data['exercises']:
        if item['exercise_id']:
            exercise(db, item['exercise_id'], user_id)
        item['id'] = item['id'] or uid()
        for obj in [item, *item['sets']]:
            obj['id'] = obj['id'] or uid()
            if obj['id'] in seen:
                fail(422, 'duplicate_stable_id')
            seen.add(obj['id'])
    return data


def workout_view(db, obj):
    content = {key: getattr(obj, key) for key in ('actual_date', 'actual_time', 'notes')}
    content['exercises'] = []
    content['missing_information'] = {}
    for row in db.scalars(select(WorkoutExercise).where(WorkoutExercise.workout_id == obj.id).order_by(WorkoutExercise.position)):
        item = {key: getattr(row, key) for key in ('id', 'exercise_id', 'weight_mode', 'weight_scope', 'name_snapshot')}
        item['sets'] = []
        for group in db.scalars(select(WorkoutSet).where(WorkoutSet.workout_exercise_id == row.id).order_by(WorkoutSet.position)):
            item['sets'].append({'id': group.id, 'kind': group.kind, 'weight_kg': str(Decimal(group.weight_grams) / 1000) if group.weight_grams is not None else None, 'reps': group.reps, 'notes': group.notes})
        content['exercises'].append(item)
    return {'id': obj.id, 'version': obj.version, 'status': obj.status, 'deleted_at': obj.deleted_at, 'created_at': obj.created_at, 'content': content}


def editable_content(view):
    content = view['content']
    for item in content['exercises']:
        item.pop('name_snapshot', None)
    return WorkoutContent.model_validate(content)


def delete_workout(db, user_id, object_id, expected_version):
    """Hide immediately; retain the record and children for seven days."""
    from ...models import now
    row = owned(db, Workout, object_id, user_id)
    version(row, expected_version)
    row.status = 'closed'
    row.deleted_at = now()
    row.version += 1
    db.flush()
    return {'deleted': True, 'id': object_id}


def purge_expired_workouts(db, user_id=None, at=None):
    """Purge in the caller's write transaction, including foreign-key references."""
    from datetime import datetime, timedelta, timezone
    from ...models import WorkoutDraft
    cutoff = ((at or datetime.now(timezone.utc)) - timedelta(days=7)).isoformat()
    query = select(Workout).where(Workout.status == 'closed', Workout.deleted_at <= cutoff)
    if user_id is not None:
        query = query.where(Workout.user_id == user_id)
    rows = list(db.scalars(query))
    for row in rows:
        for draft in db.scalars(select(WorkoutDraft).where(
                (WorkoutDraft.original_id == row.id) | (WorkoutDraft.result_id == row.id))):
            if draft.original_id == row.id:
                draft.original_id = draft.original_version = None
            if draft.result_id == row.id:
                draft.result_id = None
            draft.status = 'cancelled'
            draft.version += 1
        db.flush()
        ids = select(WorkoutExercise.id).where(WorkoutExercise.workout_id == row.id)
        db.execute(delete(WorkoutSet).where(WorkoutSet.workout_exercise_id.in_(ids)), execution_options={'synchronize_session': False})
        db.execute(delete(WorkoutExercise).where(WorkoutExercise.workout_id == row.id), execution_options={'synchronize_session': False})
        db.delete(row)
        db.flush()
    return len(rows)


def validate_exercise_references(db, user_id, data, obj=None):
    """Only the same historical exercise entry may retain an archived reference."""
    previous = {row.id: row.exercise_id for row in db.scalars(
        select(WorkoutExercise).where(WorkoutExercise.workout_id == obj.id))} if obj else {}
    for item in data['exercises']:
        if item['exercise_id']:
            retained = previous.get(item.get('id')) == item['exercise_id']
            exercise(db, item['exercise_id'], user_id, active=not retained)


def save_workout(db, user_id, data, obj=None):
    validate_exercise_references(db, user_id, data, obj)
    # Validate all referenced objects and IDs before replacing any rows.
    previous = workout_view(db, obj) if obj else None
    old_names = {i['id']: i for i in previous['content']['exercises']} if previous else {}
    for item in data['exercises']:
        existing = db.get(WorkoutExercise, item['id'])
        if existing and (obj is None or existing.workout_id != obj.id):
            fail(409, 'stable_id_conflict')
        for group in item['sets']:
            existing_set = db.get(WorkoutSet, group['id'])
            if existing_set:
                parent = db.get(WorkoutExercise, existing_set.workout_exercise_id)
                if obj is None or parent.workout_id != obj.id:
                    fail(409, 'stable_id_conflict')
        if item['exercise_id']:
            row = exercise(db, item['exercise_id'], user_id)
        else:
            if not item['confirm_create']:
                fail(422, 'custom_exercise_confirmation_required')
            row = Exercise(owner_id=user_id, name=item['custom_name'])
            db.add(row)
            db.flush()
        item['exercise_id'] = row.id
        old = old_names.get(item['id'])
        item['name_snapshot'] = old['name_snapshot'] if old and old['exercise_id'] == row.id else row.name
    if obj is None:
        obj = Workout(user_id=user_id, actual_date=data['actual_date'], actual_time=data['actual_time'], notes=data['notes'])
        db.add(obj)
        db.flush()
    else:
        ids = select(WorkoutExercise.id).where(WorkoutExercise.workout_id == obj.id)
        db.execute(delete(WorkoutSet).where(WorkoutSet.workout_exercise_id.in_(ids)), execution_options={'synchronize_session': False})
        db.execute(delete(WorkoutExercise).where(WorkoutExercise.workout_id == obj.id), execution_options={'synchronize_session': False})
        db.flush()
        db.expunge_all()
        obj = db.get(Workout, obj.id)
        obj.version += 1
    obj.actual_date, obj.actual_time, obj.notes = data['actual_date'], data['actual_time'], data['notes']
    for position, item in enumerate(data['exercises']):
        db.add(WorkoutExercise(id=item['id'], workout_id=obj.id, exercise_id=item['exercise_id'], position=position, name_snapshot=item['name_snapshot'], weight_mode=item['weight_mode'], weight_scope=item['weight_scope']))
        db.flush()
        for index, group in enumerate(item['sets']):
            db.add(WorkoutSet(id=group['id'], workout_exercise_id=item['id'], position=index, kind=group['kind'], weight_grams=int(Decimal(group['weight_kg']) * 1000) if group['weight_kg'] is not None else None, reps=group['reps'], notes=group['notes']))
    db.flush()
    return obj
