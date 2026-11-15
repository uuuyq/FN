"""Runtime context assembly: system prompt, context JSON and full history.

Every model call receives the fixed system prompt, one context user message,
the complete persisted history ordered by sequence, and this turn's new tool
messages. Nothing is truncated; over-budget requests fail with a stable error.
"""
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select

from ..models import Message, User, UserEquipment
from ..services import fail
from . import provider as provider_module

PROMPTS = Path(__file__).resolve().parent / 'prompts'
OUTPUT_RESERVE_TOKENS = 4000
MAX_OUTPUT_TOKENS = 16000
MAX_REQUEST_BYTES = 2 * 1024 * 1024

READ_ONLY_NOTE = '\n本轮为只读模式，可以查询和解释，不能发起变更确认。'


def system_prompt(read_only=False):
    text = (PROMPTS / 'system.md').read_text(encoding='utf-8').strip()
    return text + READ_ONLY_NOTE if read_only else text


def context_prompt(runtime):
    template = (PROMPTS / 'context.md').read_text(encoding='utf-8')
    return template.replace('{{ context_json }}', json.dumps(runtime, ensure_ascii=False))


def runtime_context(db, user_id, mode, pending_action=None):
    from ..schemas import Profile
    user = db.get(User, user_id)
    profile = Profile(version=user.profile_version, **(user.profile or {})).model_dump(mode='json')
    from ..modules.catalog.service import list_exercises
    catalog = list_exercises(db, user_id)
    return {'today': datetime.now(ZoneInfo(profile['timezone'])).date().isoformat(),
            'timezone': profile['timezone'],
            'mode': mode,
            'profile': profile,
            'equipment': [{'id': row.id, 'name': row.name, 'equipment_id': row.equipment_id} for row in db.scalars(
                select(UserEquipment).where(UserEquipment.user_id == user_id))],
            'catalog': catalog,
            'pending_action': pending_action}


def estimate_tokens(text):
    """Conservative estimate: one token per CJK char, one per three other chars."""
    cjk = sum(1 for ch in text if ord(ch) > 0x2E80)
    return cjk + (len(text) - cjk) // 3 + 1


def budget_usage(messages, tool_schemas):
    used = sum(estimate_tokens(json.dumps(message, ensure_ascii=False)) for message in messages)
    used += estimate_tokens(json.dumps(tool_schemas, ensure_ascii=False))
    return used


def check_budget(messages, tool_schemas):
    """Runs before every model call, including rounds after tool results."""
    if budget_usage(messages, tool_schemas) > provider_module.context_limit() - OUTPUT_RESERVE_TOKENS \
            or len(json.dumps(messages, ensure_ascii=False).encode()) > MAX_REQUEST_BYTES:
        fail(422, 'context_too_large')


def output_budget(messages, tool_schemas):
    """Output tokens for this request; never larger than the reserved budget."""
    return max(256, min(MAX_OUTPUT_TOKENS,
                        provider_module.context_limit() - budget_usage(messages, tool_schemas)))



def resolved_tool_content(content, outcomes):
    """Project durable confirmation outcomes onto their original tool results."""
    try:
        pending = json.loads(content)
    except (ValueError, TypeError):
        return content
    if not isinstance(pending, dict) or not isinstance(pending.get('data'), dict):
        return content
    outcome = outcomes.get(pending['data'].get('action_id'))
    if outcome is None:
        return content
    result = {'ok': outcome['status'] == 'confirmed', 'data': {
        'status': outcome['status'], 'action_id': outcome['action_id'], 'result': outcome.get('result')}}
    receipt = outcome.get('result')
    if isinstance(receipt, dict) and receipt.get('error'):
        result['error'] = receipt['error']
    return json.dumps(result, ensure_ascii=False)


def assemble(db, conversation_id, runtime, tool_schemas, read_only=False):
    messages = [{'role': 'system', 'content': system_prompt(read_only)},
                {'role': 'user', 'content': context_prompt(runtime)}]
    rows = db.scalars(select(Message).where(
        Message.conversation_id == conversation_id).order_by(Message.sequence)).all()
    outcomes = {row.event_data['action_id']: row.event_data for row in rows
                if row.event_kind == 'action_result' and row.event_data and row.event_data.get('action_id')}
    for row in rows:
        if row.role == 'user':
            messages.append({'role': 'user', 'content': row.content})
        elif row.role == 'assistant':
            if row.tool_calls:
                messages.append({'role': 'assistant', 'content': row.content or None, 'tool_calls': [
                    {'id': call['id'], 'type': 'function',
                     'function': {'name': call['name'], 'arguments': json.dumps(call['arguments'], ensure_ascii=False)}}
                    for call in row.tool_calls]})
            else:
                messages.append({'role': 'assistant', 'content': row.content})
        elif row.role == 'tool':
            messages.append({'role': 'tool', 'tool_call_id': row.tool_call_id,
                             'content': resolved_tool_content(row.content, outcomes)})
        elif row.role == 'event' and row.event_kind != 'action_result':
            messages.append({'role': 'assistant', 'content': '[服务端操作结果] ' + row.content})
    check_budget(messages, tool_schemas)
    return messages


def fresh_messages(db, user_id, conversation_id, mode, tool_schemas, read_only=False):
    from . import actions as actions_module
    current = actions_module.pending(db, conversation_id)
    card = {'action_id': current[0].id, 'operation': current[0].operation,
            'summary': current[0].summary, 'created_at': current[0].created_at} if current else None
    runtime = runtime_context(db, user_id, mode, pending_action=card)
    return assemble(db, conversation_id, runtime, tool_schemas, read_only=read_only)
