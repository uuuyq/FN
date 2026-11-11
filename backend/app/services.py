import hashlib
import json

from fastapi import HTTPException

from .errors import error_detail
from .models import Exercise, RequestReceipt, Workout


def fail(status, code, **details):
    raise HTTPException(status, detail=error_detail(code, **details))


def owned(db, model, object_id, user_id):
    obj = db.get(model, object_id)
    if obj is None or obj.user_id != user_id or (model is Workout and obj.status != 'active'):
        fail(404, 'not_found')
    return obj


def version(obj, expected, field='version'):
    if getattr(obj, field) != expected:
        fail(409, 'version_conflict', latest_version=getattr(obj, field))


def exercise(db, object_id, user_id, active=False):
    obj = db.get(Exercise, object_id)
    if obj is None or obj.owner_id not in (None, user_id):
        fail(404, 'exercise_not_found')
    if active and obj.archived:
        fail(409, 'exercise_archived')
    return obj


def serialize(obj):
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}


def idempotent(db, user_id, request_id, operation, body, action):
    fingerprint = hashlib.sha256(json.dumps([operation, body], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    receipt = db.get(RequestReceipt, (user_id, request_id))
    if receipt:
        if receipt.fingerprint != fingerprint:
            fail(409, 'request_id_reused')
        return receipt.result
    result = action()
    db.add(RequestReceipt(user_id=user_id, request_id=request_id, fingerprint=fingerprint, result=result))
    db.flush()
    return result
