"""Catalog storage and SQL queries shared by HTTP and other callers."""
from sqlalchemy import and_, func, literal, select, union_all

from ...models import (PublicExercise, UserExercise, UserExercisePreference,
                       Equipment, UserEquipment, normalize_exercise_text)
from ...services import fail, version, serialize


def get_exercise(db, user_id, exercise_id):
    row = db.get(PublicExercise, exercise_id)
    if row is None:
        row = db.get(UserExercise, exercise_id)
    if row is None or row.owner_id not in (None, user_id):
        fail(404, 'exercise_not_found')
    return row


def preference_target(row):
    if isinstance(row, PublicExercise):
        return {'public_exercise_id': row.id}
    return {'user_exercise_id': row.id}


def get_preference(db, user_id, row):
    conditions = [getattr(UserExercisePreference, key) == value
                  for key, value in preference_target(row).items()]
    return db.scalar(select(UserExercisePreference).where(
        UserExercisePreference.user_id == user_id, *conditions))


def exercise_query(user_id, *, active=None, q='', exercise_id=None):
    """Return a composable union with one joined preference per exercise."""
    pref = UserExercisePreference
    branches = []
    for model, target in ((PublicExercise, pref.public_exercise_id),
                          (UserExercise, pref.user_exercise_id)):
        owner = literal(None) if model is PublicExercise else model.user_id
        stmt = select(
            model.id.label('id'), model.name.label('name'), model.aliases, model.primary_muscles,
            model.secondary_muscles, model.equipment, model.description,
            model.version, owner.label('owner_id'),
            func.coalesce(pref.active, False).label('active'),
            func.coalesce(pref.version, 1).label('preference_version'),
        ).select_from(model).join(pref, and_(
            target == model.id, pref.user_id == user_id), isouter=active is not True)
        if model is UserExercise:
            stmt = stmt.where(model.user_id == user_id)
        if active is True:
            stmt = stmt.where(pref.active.is_(True))
        elif active is False:
            stmt = stmt.where(func.coalesce(pref.active, False).is_(False))
        if q:
            stmt = stmt.where(model.search_text.contains(normalize_exercise_text(q), autoescape=True))
        if exercise_id is not None:
            stmt = stmt.where(model.id == exercise_id)
        branches.append(stmt)
    return union_all(*branches)


def query_exercises(db, user_id, *, active=None, q='', offset=0, limit=50):
    """SQL-filtered paginated list, with a separate total count."""
    if offset < 0 or not 1 <= limit <= 200 or len(q) > 100:
        fail(422, 'invalid_pagination')
    rows = exercise_query(user_id, active=active, q=q)
    total = db.scalar(select(func.count()).select_from(rows.subquery()))
    items = db.execute(rows.order_by('name', 'id').offset(offset).limit(limit)).mappings().all()
    return {'items': [dict(row) for row in items], 'total': total}


def list_exercises(db, user_id, *, active=None):
    """Return the complete visible catalog. active=True limits it to enabled rows."""
    rows = exercise_query(user_id, active=active)
    return [dict(row) for row in db.execute(
        rows.order_by('name', 'id')).mappings()]


def catalog_view(db, row, user_id):
    rows = exercise_query(user_id, exercise_id=row.id)
    return dict(db.execute(rows).mappings().one())


def create_exercise(db, user_id, body):
    values = body.model_dump()
    normalized = normalize_exercise_text(values['name'])
    if db.scalar(select(UserExercise.id).where(
            UserExercise.user_id == user_id, UserExercise.normalized_name == normalized)):
        fail(409, 'exercise_name_taken')
    row = UserExercise(user_id=user_id, **values)
    db.add(row)
    db.flush()
    db.add(UserExercisePreference(user_id=user_id, user_exercise_id=row.id, active=True))
    db.flush()
    return row


def update_exercise(db, user_id, exercise_id, body):
    row = get_exercise(db, user_id, exercise_id)
    if isinstance(row, PublicExercise):
        fail(403, 'shared_exercise_readonly')
    version(row, body.version)
    if db.scalar(select(UserExercise.id).where(
            UserExercise.user_id == user_id,
            UserExercise.normalized_name == normalize_exercise_text(body.name),
            UserExercise.id != row.id)):
        fail(409, 'exercise_name_taken')
    for key, value in body.model_dump(exclude={'version'}).items():
        setattr(row, key, value)
    row.version += 1
    db.flush()
    return row


def update_preferences(db, user_id, body):
    if len({item.exercise_id for item in body.items}) != len(body.items):
        fail(422, 'duplicate_exercise')
    result = []
    for item in body.items:
        row = get_exercise(db, user_id, item.exercise_id)
        pref = get_preference(db, user_id, row)
        if pref is None:
            pref = UserExercisePreference(user_id=user_id, version=1, **preference_target(row))
            db.add(pref)
        version(pref, item.version)
        pref.active = item.active
        pref.version += 1
        db.flush()
        result.append(catalog_view(db, row, user_id))
    return {'items': result}


def add_equipment(db, user_id, body):
    if body.equipment_id and not db.get(Equipment, body.equipment_id):
        fail(404, 'equipment_not_found')
    row = UserEquipment(user_id=user_id, **body.model_dump())
    db.add(row)
    db.flush()
    return serialize(row)
