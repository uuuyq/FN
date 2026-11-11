"""Turn lifecycle: creation, lease, concurrency, retry and views."""
import time
from sqlalchemy import func, select

from ..errors import error_message
from ..models import Message, Turn, uid
from ..services import owned, fail
from . import actions as actions_module
from . import conversations

LEASE_SECONDS = 200
GLOBAL_RUNNING_LIMIT = 4


def turn_view(row):
    result = dict(row.result or {})
    return {'id': row.id, 'conversation_id': row.conversation_id, 'status': row.status,
            'error': row.error, 'result': result, 'created_at': row.created_at,
            'error_message': error_message(row.error) if row.error else None,
            'mode': (row.context or {}).get('mode', 'edit')}


def expire(db, conversation_id):
    for row in db.scalars(select(Turn).where(
            Turn.conversation_id == conversation_id, Turn.status == 'running',
            Turn.deadline <= int(time.time()))):
        row.status, row.error, row.token = 'interrupted', 'execution_expired', uid()
    db.flush()


def capacity(db):
    running = db.scalar(select(func.count()).select_from(Turn).where(
        Turn.status == 'running', Turn.deadline > int(time.time())))
    if running >= GLOBAL_RUNNING_LIMIT:
        fail(429, 'model_capacity', retryable=True)


def _create(db, user_id, conversation_id, mode, selected_date, text):
    conversation = conversations.conversation(db, conversation_id, user_id)
    expire(db, conversation_id)
    if db.scalar(select(Turn.id).where(Turn.conversation_id == conversation_id, Turn.status == 'running')):
        fail(409, 'conversation_busy')
    capacity(db)
    actions_module.supersede(db, conversation_id)
    conversations.repair_partial_tool_calls(db, conversation_id)
    row = Turn(user_id=user_id, conversation_id=conversation_id, token=uid(),
               deadline=int(time.time()) + LEASE_SECONDS,
               context={'mode': mode, 'selected_date': selected_date})
    db.add(row)
    db.flush()
    conversations.add_message(db, conversation_id, row.id, 'user', content=text)
    return turn_view(row)


def start(db, user_id, conversation_id, body):
    return _create(db, user_id, conversation_id, body.mode,
                   body.selected_date.isoformat() if body.selected_date else None, body.text)


def retry(db, user_id, object_id):
    row = owned(db, Turn, object_id, user_id)
    conversations.conversation(db, row.conversation_id, user_id)
    expire(db, row.conversation_id)
    if row.status not in ('failed', 'interrupted'):
        fail(409, 'turn_not_retryable')
    # Retry keeps the original user message; a later user turn wins.
    own_message = db.scalar(select(Message.sequence).where(
        Message.turn_id == row.id, Message.role == 'user').order_by(Message.sequence).limit(1))
    later = db.scalar(select(Message.id).where(
        Message.conversation_id == row.conversation_id, Message.role == 'user',
        Message.turn_id != row.id, Message.sequence > (own_message or 0)))
    if later or own_message is None:
        fail(409, 'turn_not_retryable')
    if db.scalar(select(Turn.id).where(Turn.conversation_id == row.conversation_id, Turn.status == 'running')):
        fail(409, 'conversation_busy')
    capacity(db)
    conversations.repair_partial_tool_calls(db, row.conversation_id)
    row.status, row.error, row.token, row.deadline = 'running', None, uid(), int(time.time()) + LEASE_SECONDS
    return turn_view(row)
