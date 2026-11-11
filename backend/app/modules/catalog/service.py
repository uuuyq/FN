from ...models import ExercisePreference, Equipment, UserEquipment
from ...services import exercise, version, fail, serialize


def catalog_view(db, row, user_id):
    pref = db.get(ExercisePreference, (user_id, row.id))
    return {**serialize(row), 'available': pref.available if pref else False, 'preference_version': pref.version if pref else 1, 'effective_selected': bool(pref and pref.available and not row.archived)}


def update_preferences(db, user_id, body):
    if len({item.exercise_id for item in body.items}) != len(body.items):
        fail(422, 'duplicate_exercise')
    result = []
    for item in body.items:
        row = exercise(db, item.exercise_id, user_id)
        pref = db.get(ExercisePreference, (user_id, row.id))
        if not pref:
            pref = ExercisePreference(user_id=user_id, exercise_id=row.id, version=1)
            db.add(pref)
        version(pref, item.version)
        pref.available = item.available
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
