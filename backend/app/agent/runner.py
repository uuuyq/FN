"""Bounded serial agent loop. Model calls run outside database transactions."""
import asyncio
import json
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..core.database import write_transaction
from ..models import Turn, uid
from . import context
from .conversations import add_message
from .contracts import tool_result
from .provider import ProviderError
from .tools import ToolContext, build_registry
from .tools import executor

LIMITS = {'model_calls': 8, 'tool_calls': 12, 'total_seconds': 180, 'call_timeout': 65}


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ProviderError('model_timeout')
    return remaining


class TurnInactive(Exception):
    """Another state owns the turn; stop without touching it."""


class LeaseExpired(Exception):
    """The turn lease ran out; mark the turn interrupted."""


def _alive(db, turn_id, user_id, token):
    row = db.get(Turn, turn_id)
    if row is None or row.user_id != user_id or row.status != 'running' or row.token != token:
        raise TurnInactive()
    if row.deadline <= int(time.time()):
        raise LeaseExpired()
    return row


def _finish(db, turn_id, user_id, token, status, result=None, error=None):
    row = _alive(db, turn_id, user_id, token) if status == 'succeeded' else db.get(Turn, turn_id)
    if row is None or row.token != token:
        return
    row.status, row.result, row.error = status, result, error
    row.token = uid()


async def run(app, turn_id, user_id, token):
    """Execute one turn to completion: reply, confirmation card, or failure."""
    engine = app.state.engine
    deadline = time.monotonic() + LIMITS['total_seconds']
    model_calls = tool_calls_used = 0
    messages = None
    registry = build_registry()
    try:
        while True:
            _remaining(deadline)
            if model_calls >= LIMITS['model_calls'] or tool_calls_used >= LIMITS['tool_calls']:
                raise ProviderError('agent_loop_limit')
            with write_transaction(engine) as db:
                row = _alive(db, turn_id, user_id, token)
                read_only = (row.context or {}).get('mode', 'edit') == 'read'
                schemas = registry.schemas(read_only)
                if messages is None:
                    messages = context.fresh_messages(db, user_id, row.conversation_id,
                        (row.context or {}).get('mode', 'edit'), (row.context or {}).get('selected_date'),
                        schemas, read_only=read_only)
            model_calls += 1
            # Every round re-checks the input budget and caps output tokens to
            # the actually remaining room, not a fixed maximum.
            context.check_budget(messages, schemas)
            config = _user_config(engine, user_id)
            remaining = _remaining(deadline)
            reply = await asyncio.wait_for(app.state.ai_provider.generate(messages, schemas, config,
                timeout=min(remaining, LIMITS['call_timeout']),
                max_tokens=context.output_budget(messages, schemas)), timeout=remaining)
            _remaining(deadline)
            if reply.type == 'text':
                with write_transaction(engine) as db:
                    _alive(db, turn_id, user_id, token)
                    _remaining(deadline)
                    add_message(db, row.conversation_id, turn_id, 'assistant', content=reply.content)
                    _remaining(deadline)
                    _finish(db, turn_id, user_id, token, 'succeeded', result={'type': 'reply'})
                return
            names = [call.name for call in reply.calls]
            over_budget = len(reply.calls) > LIMITS['tool_calls'] - tool_calls_used
            if over_budget or executor.batch_needs_single(names, registry):
                # A batch containing a write tool must hold exactly one call;
                # every call in the batch gets a correctable error result.
                error = {'code': 'batch_write_single', 'message': '包含写操作的批次只能有一个工具调用，请单独调用。'}
                if over_budget:
                    error = {'code': 'tool_call_limit', 'message': '调用额度不足，本批次未执行。'}
                tool_calls_used += len(reply.calls)
                with write_transaction(engine) as db:
                    _alive(db, turn_id, user_id, token)
                    _remaining(deadline)
                    messages.append({'role': 'assistant', 'content': None, 'tool_calls': [
                        {'id': call.id, 'type': 'function',
                         'function': {'name': call.name, 'arguments': json.dumps(call.arguments, ensure_ascii=False)}}
                        for call in reply.calls]})
                    add_message(db, row.conversation_id, turn_id, 'assistant',
                        tool_calls=[executor.build_payload(call) for call in reply.calls])
                    for call in reply.calls:
                        result = tool_result(False, error=error)
                        add_message(db, row.conversation_id, turn_id, 'tool',
                            content=executor.result_text(result), tool_call_id=call.id)
                        messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': executor.result_text(result)})
                    if over_budget:
                        _finish(db, turn_id, user_id, token, 'failed', error='agent_loop_limit')
                if over_budget:
                    return
                continue
            # Serial execution: persist the assistant call batch, then every
            # result. Read-only batches execute all calls; a write call in a
            # batch was already rejected above, so at most one card is created.
            with write_transaction(engine) as db:
                _alive(db, turn_id, user_id, token)
                _remaining(deadline)
                tool_calls_used += len(reply.calls)
                add_message(db, row.conversation_id, turn_id, 'assistant',
                    content=reply.content or '',
                    tool_calls=[executor.build_payload(call) for call in reply.calls])
                messages.append({'role': 'assistant', 'content': reply.content or None,
                    'tool_calls': [{'id': call.id, 'type': 'function',
                        'function': {'name': call.name, 'arguments': json.dumps(call.arguments, ensure_ascii=False)}}
                        for call in reply.calls]})
                ctx = ToolContext(db=db, user_id=user_id, conversation_id=row.conversation_id,
                                  turn_id=turn_id, mode=(row.context or {}).get('mode', 'edit'))
                action = None
                for call in reply.calls:
                    _remaining(deadline)
                    _alive(db, turn_id, user_id, token)
                    result, action = executor.run(ctx, registry, call.name, call.arguments)
                    _remaining(deadline)
                    add_message(db, row.conversation_id, turn_id, 'tool',
                        content=executor.result_text(result), tool_call_id=call.id)
                    messages.append({'role': 'tool', 'tool_call_id': call.id, 'content': executor.result_text(result)})
                    if action is not None:
                        break
                if action is not None:
                    _remaining(deadline)
                    _finish(db, turn_id, user_id, token, 'succeeded', result={
                        'type': 'confirmation_required', 'action_id': action.id,
                        'operation': action.operation, 'status': action.status,
                        'version': action.version, 'summary': action.summary,
                        'details': action.details, 'allowed_operations': ['confirm', 'cancel']})
                    return
    except TimeoutError:
        _mark(engine, turn_id, user_id, token, 'failed', 'model_timeout')
    except LeaseExpired:
        _mark(engine, turn_id, user_id, token, 'interrupted', 'execution_expired')
    except TurnInactive:
        return
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {}
        code = detail.get('code', 'model_result_rejected')
        _mark(engine, turn_id, user_id, token, 'conflict' if error.status_code == 409 else 'failed', code)
    except ProviderError as error:
        _mark(engine, turn_id, user_id, token, 'failed', error.code)
    except asyncio.CancelledError:
        _mark(engine, turn_id, user_id, token, 'interrupted', 'execution_expired')
        raise
    except Exception:
        _mark(engine, turn_id, user_id, token, 'failed', 'model_failed')


def _mark(engine, turn_id, user_id, token, state, code):
    # Raw exception messages may contain provider bodies or credentials.
    with write_transaction(engine) as db:
        row = db.get(Turn, turn_id)
        if row is not None and row.user_id == user_id and row.status == 'running' and row.token == token:
            row.status, row.error, row.token = state, code, uid()


def _user_config(engine, user_id):
    with Session(engine) as db:
        from ..models import User
        config = db.get(User, user_id).ai_config or {}
    return config if all(config.get(field) for field in ('api_key', 'model', 'base_url')) else None
