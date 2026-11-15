"""Operation history and server-owned undo."""
from pydantic import Field
from ...schemas import Schema
from .. import operations
from .registry import Tool, WriteSummary

class ListOperations(Schema):
    workout_id: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)

class UndoOperation(WriteSummary):
    operation_id: str = Field(description='最近七天成功执行的训练操作 ID，由写入回执或 list_operations 获取')

def validate_undo(ctx, params):
    operations.undo_target(ctx, params.operation_id)

def undo_summary(ctx, payload):
    row = operations.undo_target(ctx, payload['operation_id'])
    return '撤销：' + row.summary

def undo_details(ctx, payload):
    row = operations.undo_target(ctx, payload['operation_id'])
    return {'operation_id': row.id, 'workout_id': row.workout_id, 'original_summary': row.summary,
            'effect': '软删除新增训练，保留自定义动作目录项' if row.operation == 'create_workout' else '恢复操作前的完整训练记录'}

LIST_OPERATIONS = Tool(name='list_operations', description='分页查询最近七天成功的 Agent 训练操作及当前可撤销状态。',
    model=ListOperations, kind='read', execution='direct', execute=operations.list_operations)
UNDO_OPERATION = Tool(name='undo_operation', description='撤销一次成功的训练新增、修改或删除。仅限七天内且目标未再修改的操作，后端恢复快照，需要确认。',
    model=UndoOperation, kind='write', execution='user_confirmation', execute=operations.execute_undo,
    validate=validate_undo, operation=lambda payload: 'undo_operation', summary=undo_summary, details=undo_details)
