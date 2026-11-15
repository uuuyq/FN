from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Equipment, UserEquipment
from ...schemas import ExerciseInput, ExerciseUpdate, Version, PreferenceBatch, EquipmentInput, EquipmentUpdate
from ...services import fail, version, owned, serialize
from . import service

RequestId = Annotated[str, Header(alias='X-Request-ID', min_length=8, max_length=100)]


def register(app, engine, identity, mutate, secure, password_hasher, dummy_hash):
    @app.get('/api/exercises')
    def list_exercises(q: str = '', active: bool | None = None, offset: int = 0,
                       limit: int = 50, user_id=Depends(identity)):
        with Session(engine) as db:
            return service.query_exercises(db, user_id, q=q, active=active, offset=offset, limit=limit)

    @app.get('/api/exercises/{object_id}')
    def get_exercise(object_id: str, user_id=Depends(identity)):
        with Session(engine) as db:
            return service.catalog_view(db, service.get_exercise(db, user_id, object_id), user_id)

    @app.post('/api/exercises')
    def create_exercise(body: ExerciseInput, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            return service.catalog_view(db, service.create_exercise(db, user_id, body), user_id)
        return mutate(request, user_id, x_request_id, body, action)

    @app.put('/api/exercises/{object_id}')
    def update_exercise(object_id: str, body: ExerciseUpdate, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            return service.catalog_view(db, service.update_exercise(db, user_id, object_id, body), user_id)
        return mutate(request, user_id, x_request_id, body, action)

    @app.put('/api/exercise-preferences')
    def preferences(body: PreferenceBatch, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        return mutate(request, user_id, x_request_id, body,
                      lambda db: service.update_preferences(db, user_id, body))

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
            return service.add_equipment(db, user_id, body)
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

