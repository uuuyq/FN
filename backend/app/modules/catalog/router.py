from .service import catalog_view, update_preferences, add_equipment as create_user_equipment

from fastapi import Depends, Header, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models import Exercise, Equipment, UserEquipment
from ...schemas import ExerciseInput, ExerciseUpdate, Version, PreferenceBatch, EquipmentInput, EquipmentUpdate
from ...services import fail, version, owned, exercise, serialize
from typing import Annotated


RequestId = Annotated[str, Header(alias="X-Request-ID", min_length=8, max_length=100)]

def register(app, engine, identity, mutate, secure, password_hasher, dummy_hash):
    @app.get('/api/exercises')
    def list_exercises(q: str = '', available: bool | None = None, offset: int = 0, limit: int = 50, user_id=Depends(identity)):
        if offset < 0 or not 1 <= limit <= 200 or len(q) > 100:
            fail(422, 'invalid_pagination')
        with Session(engine) as db:
            rows = [catalog_view(db, row, user_id) for row in db.scalars(select(Exercise).where(or_(Exercise.owner_id.is_(None), Exercise.owner_id == user_id)).order_by(Exercise.name, Exercise.id))]
            rows = [row for row in rows if (not q or any(q.casefold() in name.casefold() for name in [row['name'], *row['aliases']])) and (available is None or row['available'] == available)]
            return {'items': rows[offset:offset+limit], 'total': len(rows)}

    @app.get('/api/exercises/{object_id}')
    def get_exercise(object_id: str, user_id=Depends(identity)):
        with Session(engine) as db:
            return catalog_view(db, exercise(db, object_id, user_id), user_id)

    @app.post('/api/exercises')
    def create_exercise(body: ExerciseInput, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = Exercise(owner_id=user_id, **body.model_dump())
            db.add(row)
            db.flush()
            return catalog_view(db, row, user_id)
        return mutate(request, user_id, x_request_id, body, action)

    @app.put('/api/exercises/{object_id}')
    def update_exercise(object_id: str, body: ExerciseUpdate, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = exercise(db, object_id, user_id)
            if row.owner_id != user_id:
                fail(403, 'shared_exercise_readonly')
            version(row, body.version)
            for key, value in body.model_dump(exclude={'version'}).items():
                setattr(row, key, value)
            row.version += 1
            return catalog_view(db, row, user_id)
        return mutate(request, user_id, x_request_id, body, action)

    @app.post('/api/exercises/{object_id}/archive')
    def archive(object_id: str, body: Version, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = exercise(db, object_id, user_id)
            if row.owner_id != user_id:
                fail(403, 'shared_exercise_readonly')
            version(row, body.version)
            if not row.archived:
                row.archived, row.version = True, row.version + 1
            return catalog_view(db, row, user_id)
        return mutate(request, user_id, x_request_id, body, action)

    @app.put('/api/exercise-preferences')
    def preferences(body: PreferenceBatch, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            return update_preferences(db, user_id, body)
        return mutate(request, user_id, x_request_id, body, action)

    @app.get('/api/equipment')
    def equipment_catalog(user_id=Depends(identity)):
        with Session(engine) as db:
            return {'items': [serialize(row) for row in db.scalars(select(Equipment).order_by(Equipment.name))]}

    @app.get('/api/user-equipment')
    def user_equipment(user_id=Depends(identity)):
        with Session(engine) as db:
            return {'items': [serialize(row) for row in db.scalars(select(UserEquipment).where(UserEquipment.user_id == user_id))]}

    def equipment_values(db, body):
        if body.equipment_id and not db.get(Equipment, body.equipment_id):
            fail(404, 'equipment_not_found')
        return body.model_dump(exclude={'version'})

    @app.post('/api/user-equipment')
    def add_equipment(body: EquipmentInput, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            return create_user_equipment(db, user_id, body)
        return mutate(request, user_id, x_request_id, body, action)

    @app.put('/api/user-equipment/{object_id}')
    def update_equipment(object_id: str, body: EquipmentUpdate, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = owned(db, UserEquipment, object_id, user_id)
            version(row, body.version)
            for key, value in equipment_values(db, body).items():
                setattr(row, key, value)
            row.version += 1
            return serialize(row)
        return mutate(request, user_id, x_request_id, body, action)

    @app.delete('/api/user-equipment/{object_id}')
    def remove_equipment(object_id: str, body: Version, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = owned(db, UserEquipment, object_id, user_id)
            version(row, body.version)
            db.delete(row)
            return {'removed': True}
        return mutate(request, user_id, x_request_id, body, action)

