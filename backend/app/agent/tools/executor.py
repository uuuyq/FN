"""Serial tool execution. Read tools run directly; write tools propose only."""
import json

from fastapi import HTTPException
from pydantic import ValidationError

from ..contracts import tool_result
from .. import actions

# Errors the model can act on by changing arguments or re-reading data.
CORRECTABLE = {'validation_error', 'version_conflict', 'workout_trashed', 'exercise_not_found',
               'equipment_not_found', 'not_found', 'invalid_query', 'duplicate_exercise',
               'duplicate_stable_id', 'stable_id_conflict', 'exercise_archived', 'ambiguous_workout_target'}


def _error(code, message, field=None):
    return {'code': code, 'message': message, **({'field': field} if field else {})}


def run(ctx, registry, name, arguments):
    """Execute one tool call. Returns (result, action|None). Never raises for correctable issues."""
    tool = registry.get(name)
    if tool is None:
        return tool_result(False, error=_error('unknown_tool', '工具不存在，请使用提供的工具列表中的名称。', 'name')), None
    try:
        params = tool.model.model_validate(arguments)
    except ValidationError as error:
        first = error.errors(include_input=False, include_context=False)[0]
        field = '.'.join(str(part) for part in first['loc'])
        return tool_result(False, error=_error('validation_error', '参数不符合要求，请修正后重试。', field)), None
    try:
        if tool.kind == 'read':
            return tool_result(True, data=tool.execute(ctx, params)), None
        if ctx.mode == 'read':
            raise HTTPException(422, detail={'code': 'read_only_turn'})
        tool.validate(ctx, params)
        payload = params.model_dump(mode='json')
        action = actions.propose(ctx, tool, payload)
        return tool_result(True, data={'confirmation_required': True, 'action_id': action.id,
            'operation': action.operation, 'version': action.version, 'summary': action.summary}), action
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {}
        code = detail.get('code', 'internal_error')
        if code in CORRECTABLE:
            return tool_result(False, error=_error(code, detail.get('message', '参数无法执行，请调整后重试。'), detail.get('field'))), None
        raise


def build_payload(call):
    """Stable JSON serialization for tool-call message storage."""
    return {'id': call.id, 'name': call.name, 'arguments': call.arguments}


def result_text(result):
    return json.dumps(result, ensure_ascii=False)


def batch_needs_single(call_names, registry):
    """A batch containing a write tool must contain exactly one call."""
    if len(call_names) <= 1:
        return False
    return any(tool and tool.kind == 'write' for tool in map(registry.get, call_names))
