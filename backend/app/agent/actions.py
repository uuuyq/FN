"""Pending conversation actions: proposal, confirmation, cancellation.

Confirmation reads the stored tool name, contract version and payload, resolves
the original business function through the registry, re-checks ownership and
versions in the same transaction, and runs the change inside a SAVEPOINT.
"""
from fastapi import HTTPException
from sqlalchemy import select

from ..models import ConversationAction, Turn, now
from ..services import fail, owned, version
from .contracts import ToolError
from .conversations import add_message
from .tools import ToolContext, build_registry

TOOL_CONTRACT_VERSION = '1'


def action_view(row):
    return {'action_id': row.id, 'operation': row.operation, 'tool_name': row.tool_name,
            'status': row.status, 'version': row.version, 'summary': row.summary,
            'details': row.details, 'result': row.result,
            'created_at': row.created_at, 'completed_at': row.completed_at,
            'allowed_operations': ['confirm', 'cancel'] if row.status == 'pending' else []}


def pending(db, conversation_id):
    return db.scalars(select(ConversationAction).where(
        ConversationAction.conversation_id == conversation_id,
        ConversationAction.status == 'pending')).all()


def propose(ctx, tool, payload):
    """Store the immutable payload and build the confirmation card. No business writes."""
    for row in pending(ctx.db, ctx.conversation_id):
        row.status, row.completed_at, row.version = 'superseded', now(), row.version + 1
    row = ConversationAction(user_id=ctx.user_id, conversation_id=ctx.conversation_id,
        turn_id=ctx.turn_id, operation=tool.operation(payload), tool_name=tool.name,
        tool_contract_version=TOOL_CONTRACT_VERSION, payload=payload,
        summary=payload.get('summary') or tool.summary(ctx, payload), details=tool.details(ctx, payload))
    ctx.db.add(row)
    ctx.db.flush()
    return row


def apply(db, user_id, object_id, operation, expected_version):
    action = owned(db, ConversationAction, object_id, user_id)
    if action.status == ('confirmed' if operation == 'confirm' else 'cancelled'):
        return action_view(action)
    version(action, expected_version)
    if action.status != 'pending':
        fail(409, 'action_not_pending')
    if operation == 'confirm':
        # While newer conversation content is still processing, the old card's
        # confirmation is paused so the user cannot confirm stale intent (G14).
        if db.scalar(select(Turn.id).where(
                Turn.conversation_id == action.conversation_id, Turn.status == 'running')):
            fail(409, 'conversation_busy')
    if operation == 'cancel':
        action.status, action.completed_at, action.version = 'cancelled', now(), action.version + 1
        add_message(db, action.conversation_id, action.turn_id, 'event',
            content='已取消待确认操作：{}'.format(action.operation),
            event_kind='action_cancelled', event_data={'action_id': action.id, 'operation': action.operation})
        return action_view(action)

    registry = build_registry()
    tool = registry.get(action.tool_name)
    if tool is None or tool.execution != 'user_confirmation' or action.tool_contract_version != TOOL_CONTRACT_VERSION:
        action.status, action.completed_at, action.version = 'failed', now(), action.version + 1
        action.result = {'error': ToolError(code='action_invalid', message='待确认操作已失效。').model_dump()}
        return action_view(action)
    turn = db.get(Turn, action.turn_id)
    ctx = ToolContext(db=db, user_id=user_id, conversation_id=action.conversation_id,
                      turn_id=action.turn_id, mode=(turn.context or {}).get('mode', 'edit') if turn else 'edit')
    try:
        params = tool.model.model_validate(action.payload)
        tool.validate(ctx, params)
        nested = db.begin_nested()
        try:
            from .operations import capture_before, record_operation
            before = capture_before(ctx, action)
            receipt = tool.execute(ctx, params)
            record_operation(ctx, action, before, receipt)
            # save_workout may expunge ORM objects; re-read by primary key.
            action = db.get(ConversationAction, object_id)
            action.status, action.result, action.completed_at, action.version = 'confirmed', receipt, now(), action.version + 1
            add_message(db, action.conversation_id, action.turn_id, 'event',
                content='已确认执行 {}，结果：{}'.format(action.operation, receipt.get('summary', '完成')),
                event_kind='action_confirmed',
                event_data={'action_id': action.id, 'operation': action.operation, 'result': receipt})
            ctx.db.flush()
            nested.commit()
            return action_view(action)
        except Exception:
            nested.rollback()
            raise
    except HTTPException as error:
        action = db.get(ConversationAction, object_id)
        detail = error.detail if isinstance(error.detail, dict) else {}
        status = 'conflict' if error.status_code == 409 else 'failed'
        action.status, action.completed_at, action.version = status, now(), action.version + 1
        action.result = {'error': {'code': detail.get('code', 'internal_error'), 'message': detail.get('message', '执行失败。')}}
        add_message(db, action.conversation_id, action.turn_id, 'event',
            content='待确认操作执行失败：{}'.format(detail.get('message', '执行失败。')),
            event_kind='action_failed',
            event_data={'action_id': action.id, 'operation': action.operation,
                        'error': {'code': detail.get('code', 'internal_error')}})
        return action_view(action)
    except Exception:
        action = db.get(ConversationAction, object_id)
        action.status, action.completed_at, action.version = 'failed', now(), action.version + 1
        action.result = {'error': {'code': 'internal_error', 'message': '执行失败。'}}
        add_message(db, action.conversation_id, action.turn_id, 'event',
            content='待确认操作执行失败，请稍后重试。',
            event_kind='action_failed', event_data={'action_id': action.id, 'operation': action.operation})
        return action_view(action)
