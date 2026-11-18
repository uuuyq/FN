"""Training persistence. The caller owns the write transaction."""
from decimal import Decimal
from itertools import groupby

from sqlalchemy import delete, func, select

from ...models import PublicExercise, UserExercise, Workout, WorkoutSet, uid, now, normalize_exercise_text
from ...schemas import ExerciseInput
from ...services import exercise, fail, owned, version
from ..catalog.service import create_exercise, preference_target


def query_workouts(db, user_id, *, on=None, start_date=None, end_date=None, exercise_id=None, offset=0, limit=50):
    stmt = select(Workout).where(Workout.user_id == user_id, Workout.deleted_at.is_(None))
    if on:
        stmt = stmt.where(Workout.actual_date == on.isoformat())
    if start_date:
        stmt = stmt.where(Workout.actual_date >= start_date.isoformat())
    if end_date:
        stmt = stmt.where(Workout.actual_date <= end_date.isoformat())
    if exercise_id:
        stmt = stmt.where(select(WorkoutSet.id).where(WorkoutSet.workout_id == Workout.id,
            (WorkoutSet.public_exercise_id == exercise_id) | (WorkoutSet.user_exercise_id == exercise_id)).exists())
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.scalars(stmt.order_by(Workout.actual_date.desc(), Workout.actual_time.desc(), Workout.created_at.desc(), Workout.id.desc())
                      .offset(offset).limit(limit)).all()
    return rows, total


def normalized_content(db, user_id, content):
    data = content.model_dump(mode='json')
    seen = set()
    for item in data['exercises']:
        if item['exercise_id']:
            exercise(db, item['exercise_id'], user_id)
        for group in item['sets']:
            group['id'] = group['id'] or uid()
            if group['id'] in seen:
                fail(422, 'duplicate_stable_id')
            seen.add(group['id'])
    return data


def sets_brief(sets):
    """Aggregate consecutive identical sets: 60 kg，3组×8次；unknown stays visible."""
    import itertools
    parts = []
    for (weight, reps), groups in itertools.groupby(
            sets, key=lambda s: (s.get('weight_kg'), s.get('reps'))):
        count = len(list(groups))
        weight_text = '{} kg'.format(weight) if weight is not None else '重量未记录'
        reps_text = '{} 次'.format(reps) if reps is not None else '次数未记录'
        if count > 1:
            parts.append('{}，{}组×{}'.format(weight_text, count, reps_text))
        else:
            parts.append('{} × {}'.format(weight_text, reps_text))
    return '；'.join(parts)


def workout_view(db, obj):
    # Names come from both current catalogs, including disabled preferences.
    stmt = select(WorkoutSet, func.coalesce(PublicExercise.name, UserExercise.name)).outerjoin(
        PublicExercise, WorkoutSet.public_exercise_id == PublicExercise.id).outerjoin(
        UserExercise, WorkoutSet.user_exercise_id == UserExercise.id).where(
        WorkoutSet.workout_id == obj.id).order_by(WorkoutSet.exercise_position, WorkoutSet.set_position)
    rows = db.execute(stmt).all()
    content = {key: getattr(obj, key) for key in ('actual_date', 'actual_time', 'notes')}
    content['exercises'] = []
    content['missing_information'] = {}
    for position, groups in groupby(rows, key=lambda row: row[0].exercise_position):
        groups = list(groups)
        first, name = groups[0]
        item = {'exercise_id': first.public_exercise_id or first.user_exercise_id,
                'name': name, 'sets': []}
        for group, _ in groups:
            item['sets'].append({'id': group.id, 'kind': group.kind,
                'weight_kg': str(Decimal(group.weight_grams) / 1000) if group.weight_grams is not None else None,
                'reps': group.reps, 'notes': group.notes})
        content['exercises'].append(item)
    return {'id': obj.id, 'version': obj.version, 'deleted_at': obj.deleted_at,
            'created_at': obj.created_at, 'content': content}


def delete_workout(db, user_id, object_id, expected_version):
    row = owned(db, Workout, object_id, user_id)
    version(row, expected_version)
    row.deleted_at = now()
    row.version += 1
    db.flush()
    return {'deleted': True, 'id': object_id}


def purge_expired_workouts(db, user_id=None, at=None):
    from datetime import datetime, timedelta, timezone
    cutoff = ((at or datetime.now(timezone.utc)) - timedelta(days=7)).isoformat()
    from ...models import AgentOperation
    expired = select(AgentOperation).where(AgentOperation.created_at <= cutoff)
    if user_id is not None:
        expired = expired.where(AgentOperation.user_id == user_id)
    for operation in db.scalars(expired):
        operation.before = None
    query = select(Workout).where(Workout.deleted_at <= cutoff)
    if user_id is not None:
        query = query.where(Workout.user_id == user_id)
    rows = list(db.scalars(query))
    for row in rows:
        db.execute(delete(WorkoutSet).where(WorkoutSet.workout_id == row.id))
        db.delete(row)
    db.flush()
    return len(rows)


def validate_exercise_references(db, user_id, data):
    for item in data['exercises']:
        if item['exercise_id']:
            exercise(db, item['exercise_id'], user_id)


def save_workout(db, user_id, data, obj=None):
    validate_exercise_references(db, user_id, data)
    # Check all stable IDs before replacing the old sets.
    ids = [group['id'] for item in data['exercises'] for group in item['sets']]
    if len(ids) != len(set(ids)):
        fail(422, 'duplicate_stable_id')
    existing = db.scalars(select(WorkoutSet).where(WorkoutSet.id.in_(ids))).all()
    if any(obj is None or group.workout_id != obj.id for group in existing):
        fail(409, 'stable_id_conflict')
    targets = []
    for item in data['exercises']:
        if item['exercise_id']:
            row = exercise(db, item['exercise_id'], user_id)
        else:
            if not item['confirm_create']:
                fail(422, 'custom_exercise_confirmation_required')
            row = db.scalar(select(UserExercise).where(UserExercise.user_id == user_id,
                UserExercise.normalized_name == normalize_exercise_text(item['custom_name'])))
            if row is None:
                row = create_exercise(db, user_id, ExerciseInput(name=item['custom_name'], training_parts=item.get('training_parts', [])))
        targets.append(preference_target(row))
    if obj is None:
        obj = Workout(user_id=user_id, actual_date=data['actual_date'])
        db.add(obj)
        db.flush()
    else:
        db.execute(delete(WorkoutSet).where(WorkoutSet.workout_id == obj.id))
        db.flush()
        obj.version += 1
    obj.actual_date, obj.actual_time, obj.notes = data['actual_date'], data['actual_time'], data['notes']
    for exercise_position, (item, target) in enumerate(zip(data['exercises'], targets)):
        for set_position, group in enumerate(item['sets']):
            db.add(WorkoutSet(id=group['id'], workout_id=obj.id, **target,
                exercise_position=exercise_position, set_position=set_position, kind=group['kind'],
                weight_grams=int(Decimal(group['weight_kg']) * 1000) if group['weight_kg'] is not None else None,
                reps=group['reps'], notes=group['notes']))
    db.flush()
    return obj
