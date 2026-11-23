import hashlib
import json

from fastapi import HTTPException

from .errors import error_detail
from .models import RequestReceipt, Workout


def fail(status, code, **details):
    raise HTTPException(status, detail=error_detail(code, **details))


def owned(db, model, object_id, user_id):
    obj = db.get(model, object_id)
    if obj is None or obj.user_id != user_id or (model is Workout and obj.deleted_at is not None):
        fail(404, 'not_found')
    return obj


def version(obj, expected, field='version'):
    if getattr(obj, field) != expected:
        fail(409, 'version_conflict', latest_version=getattr(obj, field))


def exercise(db, object_id, user_id):
    from .modules.catalog.service import get_exercise
    return get_exercise(db, user_id, object_id)


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
