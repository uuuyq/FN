from datetime import date

from fastapi import Depends, Header, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ...models import Workout
from ...schemas import Version, ContentUpdate, WorkoutCreate
from ...services import fail, version, owned
from .service import normalized_content, workout_view, save_workout, delete_workout, query_workouts
from typing import Annotated


RequestId = Annotated[str, Header(alias="X-Request-ID", min_length=8, max_length=100)]

def register(app, engine, identity, mutate, secure, password_hasher, dummy_hash):
    @app.post('/api/workouts')
    def create_workout(body: WorkoutCreate, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            data = normalized_content(db, user_id, body.content)
            return workout_view(db, save_workout(db, user_id, data))
        return mutate(request, user_id, x_request_id, body, action)

    @app.get('/api/workouts')
    def list_workouts(on: date, offset: int = 0, limit: int = 50, user_id=Depends(identity)):
        if offset < 0 or not 1 <= limit <= 200:
            fail(422, 'invalid_query')
        with Session(engine) as db:
            rows, total = query_workouts(db, user_id, on=on, offset=offset, limit=limit)
            return {'items': [workout_view(db, row) for row in rows], 'total': total}

    @app.get('/api/workouts/calendar')
    def calendar(month: str, user_id=Depends(identity)):
        import re
        import calendar as cal
        if not re.fullmatch(r'\d{4}-\d{2}', month):
            fail(422, 'invalid_month')
        try:
            year, number = map(int, month.split('-'))
            first = date(year, number, 1).isoformat()
            last = date(year, number, cal.monthrange(year, number)[1]).isoformat()
        except ValueError:
            fail(422, 'invalid_month')
        with Session(engine) as db:
            rows = db.execute(select(Workout.actual_date, func.count()).where(
                Workout.user_id == user_id, Workout.deleted_at.is_(None),
                Workout.actual_date >= first, Workout.actual_date <= last
            ).group_by(Workout.actual_date)).all()
            from ...models import WorkoutSet, PublicExercise, UserExercise
            part_rows = db.execute(select(Workout.actual_date, PublicExercise.training_parts, UserExercise.training_parts)
                .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
                .outerjoin(PublicExercise, WorkoutSet.public_exercise_id == PublicExercise.id)
                .outerjoin(UserExercise, WorkoutSet.user_exercise_id == UserExercise.id)
                .where(Workout.user_id == user_id, Workout.deleted_at.is_(None),
                       Workout.actual_date >= first, Workout.actual_date <= last)).all()
            parts = {}
            for day, public, personal in part_rows:
                parts.setdefault(day, set()).update(public or personal or [])
            order = ['胸', '背', '腿', '二头', '三头', '肩', '腹']
            return {'month': month, 'training_days': len(rows),
                    'days': [{'date': day, 'count': count,
                              'parts': [part for part in order if part in parts.get(day, set())]}
                             for day, count in rows]}

    @app.get('/api/workouts/{object_id}')
    def get_workout(object_id: str, user_id=Depends(identity)):
        with Session(engine) as db:
            return workout_view(db, owned(db, Workout, object_id, user_id))

    @app.put('/api/workouts/{object_id}')
    def update_workout(object_id: str, body: ContentUpdate, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            row = owned(db, Workout, object_id, user_id)
            version(row, body.version)
            if row.deleted_at:
                fail(409, 'workout_trashed')
            return workout_view(db, save_workout(db, user_id, normalized_content(db, user_id, body.content), row))
        return mutate(request, user_id, x_request_id, body, action)

    @app.delete('/api/workouts/{object_id}')
    def delete_workout_record(object_id: str, body: Version, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            return delete_workout(db, user_id, object_id, body.version)
        return mutate(request, user_id, x_request_id, body, action)
