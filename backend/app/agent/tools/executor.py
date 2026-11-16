"""Serial scheduling using explicit tool execution strategies."""
import json

from fastapi import HTTPException
from pydantic import ValidationError

from ..contracts import ExecutionResult, ToolError
from .. import actions

# Errors the model can act on by changing arguments or re-reading data.
CORRECTABLE = {'exercise_name_taken', 'operation_already_undone', 'operation_expired', 'snapshot_missing', 'validation_error', 'version_conflict', 'workout_trashed', 'exercise_not_found',
               'equipment_not_found', 'not_found', 'invalid_query', 'duplicate_exercise',
               'duplicate_stable_id', 'stable_id_conflict', 'ambiguous_workout_target',
               'missing_key_information'}


def _error(code, message, field=None):
    return {'code': code, 'message': message, **({'field': field} if field else {})}


def run(ctx, registry, name, arguments):
    """Schedule one call and return a unified outcome. Correctable errors return to the model."""
    tool = registry.get(name)
    if tool is None:
        return ExecutionResult(error=ToolError.model_validate(_error('unknown_tool', '工具不存在，请使用提供的工具列表中的名称。', 'name')))
    try:
        params = tool.model.model_validate(arguments)
    except ValidationError as error:
        first = error.errors(include_input=False, include_context=False)[0]
        field = '.'.join(str(part) for part in first['loc'])
        return ExecutionResult(error=ToolError.model_validate(_error('validation_error', '参数不符合要求，请修正后重试。', field)))
    try:
        if tool.kind == 'write' and ctx.mode == 'read':
            raise HTTPException(422, detail={'code': 'read_only_turn'})
        if tool.validate:
            tool.validate(ctx, params)
        if tool.execution == 'direct':
            return ExecutionResult(data=tool.execute(ctx, params))
        payload = params.model_dump(mode='json', exclude_unset=tool.name == 'update_profile')
        action = actions.propose(ctx, tool, payload)
        return ExecutionResult(data={'confirmation_required': True, 'action_id': action.id,
            'operation': action.operation, 'version': action.version, 'summary': action.summary},
            action=action, continuation='await_confirmation')
    except HTTPException as error:
        detail = error.detail if isinstance(error.detail, dict) else {}
        code = detail.get('code', 'internal_error')
        if code in CORRECTABLE:
            message = detail.get('message', '参数无法执行，请调整后重试。')
            return ExecutionResult(error=ToolError.model_validate(_error(code, message, detail.get('field'))))
        raise


def build_payload(call):
    """Stable JSON serialization for tool-call message storage."""
    return {'id': call.id, 'name': call.name, 'arguments': call.arguments}


def result_text(result):
    return json.dumps(result, ensure_ascii=False)


def batch_needs_single(call_names, registry):
    """A confirmation strategy must be scheduled in its own batch."""
    if len(call_names) <= 1:
        return False
    return any(tool and tool.execution == 'user_confirmation' for tool in map(registry.get, call_names))
