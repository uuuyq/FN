"""Conversation management and full message/event storage."""
from sqlalchemy import func, select

from ..models import Conversation, Message
from ..services import owned, fail


def conversation(db, object_id, user_id):
    row = owned(db, Conversation, object_id, user_id)
    if row.deleted_at:
        fail(404, 'not_found')
    return row


def add_message(db, conversation_id, turn_id, role, content='', *, tool_calls=None,
                tool_call_id=None, event_kind=None, event_data=None):
    sequence = (db.scalar(select(func.max(Message.sequence)).where(
        Message.conversation_id == conversation_id)) or 0) + 1
    row = Message(conversation_id=conversation_id, turn_id=turn_id, role=role, content=content,
        tool_calls=tool_calls, tool_call_id=tool_call_id, sequence=sequence,
        event_kind=event_kind, event_data=event_data)
    db.add(row)
    db.flush()
    return row


def message_view(row):
    return {'id': row.id, 'turn_id': row.turn_id, 'role': row.role, 'content': row.content,
            'tool_calls': row.tool_calls, 'tool_call_id': row.tool_call_id,
            'sequence': row.sequence, 'event_kind': row.event_kind,
            'event_data': row.event_data, 'created_at': row.created_at}


def repair_partial_tool_calls(db, conversation_id):
    """Give every persisted tool call a result so the sequence stays valid."""
    results = {row.tool_call_id for row in db.scalars(select(Message).where(
        Message.conversation_id == conversation_id, Message.role == 'tool'))}
    calls = db.scalars(select(Message).where(
        Message.conversation_id == conversation_id, Message.role == 'assistant', Message.tool_calls.is_not(None)).order_by(Message.sequence)).all()
    repaired = 0
    for row in calls:
        for call in row.tool_calls or []:
            if call.get('id') not in results:
                add_message(db, conversation_id, row.turn_id, 'tool',
                    content='{"ok": false, "error": {"code": "interrupted", "message": "执行被中断，未产生结果。"}}',
                    tool_call_id=call['id'])
                repaired += 1
    return repaired
