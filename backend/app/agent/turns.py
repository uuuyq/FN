"""Turn lifecycle: creation, lease, concurrency, retry and views."""
import time
from sqlalchemy import func, select

from ..errors import error_message
from ..models import Message, Turn, uid
from ..services import owned, fail
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


def _create(db, user_id, conversation_id, mode, text):
    conversation = conversations.conversation(db, conversation_id, user_id)
    expire(db, conversation_id)
    if db.scalar(select(Turn.id).where(Turn.conversation_id == conversation_id, Turn.status == 'running')):
        fail(409, 'conversation_busy')
    capacity(db)
    # A plain new message keeps an existing pending card executable (G13);
    # only a successful new proposal supersedes it, atomically in propose().
    conversations.repair_partial_tool_calls(db, conversation_id)
    row = Turn(user_id=user_id, conversation_id=conversation_id, token=uid(),
               deadline=int(time.time()) + LEASE_SECONDS,
               context={'mode': mode})
    db.add(row)
    db.flush()
    conversations.add_message(db, conversation_id, row.id, 'user', content=text)
    return turn_view(row)


def start(db, user_id, conversation_id, body):
    return _create(db, user_id, conversation_id, body.mode, body.text)


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
    if (row.context or {}).get('source_action_id'):
        anchor = db.scalar(select(Message.sequence).where(Message.turn_id == row.id).order_by(Message.sequence).limit(1))
        later = db.scalar(select(Message.id).where(Message.conversation_id == row.conversation_id,
            Message.role == 'user', Message.sequence > (anchor or 0)))
        if later or anchor is None:
            fail(409, 'turn_not_retryable')
    elif later or own_message is None:
        fail(409, 'turn_not_retryable')
    if db.scalar(select(Turn.id).where(Turn.conversation_id == row.conversation_id, Turn.status == 'running')):
        fail(409, 'conversation_busy')
    capacity(db)
    conversations.repair_partial_tool_calls(db, row.conversation_id)
    row.status, row.error, row.token, row.deadline = 'running', None, uid(), int(time.time()) + LEASE_SECONDS
    return turn_view(row)


def continue_action(db, user_id, action):
    """Create one durable continuation for a decided action in its transaction."""
    result = dict(action.result or {})
    if result.get('continuation_turn_id'):
        return result['continuation_turn_id']
    conversations.conversation(db, action.conversation_id, user_id)
    expire(db, action.conversation_id)
    if db.scalar(select(Turn.id).where(Turn.conversation_id == action.conversation_id,
                                     Turn.status == 'running')):
        fail(409, 'conversation_busy')
    running = db.scalar(select(func.count()).select_from(Turn).where(
        Turn.status == 'running', Turn.deadline > int(time.time())))
    original = db.get(Turn, action.turn_id)
    context = dict(original.context or {}) if original else {'mode': 'edit'}
    context['source_action_id'] = action.id
    row = Turn(user_id=user_id, conversation_id=action.conversation_id, token=uid(),
               deadline=int(time.time()) + LEASE_SECONDS, context=context)
    if running >= GLOBAL_RUNNING_LIMIT:
        row.status, row.error = 'failed', 'model_capacity'
    db.add(row)
    db.flush()
    # A structured server event supplies the execution outcome without a user prompt.
    conversations.add_message(db, action.conversation_id, row.id, 'event', content='',
        event_kind='action_result', event_data={'action_id': action.id,
            'operation': action.operation, 'tool_name': action.tool_name,
            'status': action.status, 'result': action.result})
    result['continuation_turn_id'] = row.id
    action.result = result
    return row.id
