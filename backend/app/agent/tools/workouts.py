"""Workout tools. Write tools only validate and propose; execution runs on confirm."""
from datetime import date, time
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from ...schemas import Schema, WorkoutContent
from ...models import Workout
from ...services import fail, owned, version
from ...modules.workouts.service import normalized_content, workout_view, save_workout, delete_workout, query_workouts, validate_exercise_references
from .registry import Tool


class ListWorkouts(Schema):
    start: date | None = Field(default=None, description='开始日期（含），格式 YYYY-MM-DD')
    end: date | None = Field(default=None, description='结束日期（含），格式 YYYY-MM-DD')
    exercise_id: str | None = Field(default=None, description='按上下文动作目录中的 exercise_id 筛选')
    latest: bool = Field(default=False, description='为 true 时只返回最近一条记录')
    offset: int = Field(default=0, ge=0, description='分页偏移量')
    limit: int = Field(default=20, ge=1, le=50, description='每页数量，默认 20，最大 50')

    @model_validator(mode='after')
    def dates(self):
        if self.start and self.end and self.start > self.end:
            raise ValueError('Invalid date range')
        return self


class GetWorkout(Schema):
    workout_id: str = Field(description='查询结果或对话中明确指定的记录 ID')


class ToolSetInput(Schema):
    id: str | None = Field(default=None, description='修改时保留原条目 ID；新增条目不填写旧记录 ID')
    kind: Literal['working', 'warmup'] = Field(default='working',
        description='working 为正式组，warmup 为热身组；未特别说明时按正式组记录')
    weight_kg: Decimal | None = Field(default=None, ge=0, le=10000, decimal_places=3,
        description='公斤重量，十进制字符串，最多三位小数；未记录为 null，零与未记录不同')
    reps: int | None = Field(default=None, strict=True, ge=0, le=10000, description='本组次数，整数；未记录为 null')
    notes: str = Field(default='', max_length=2000, description='本组备注，如器械调整或助力方式')


class ToolExerciseInput(Schema):
    id: str | None = Field(default=None, description='修改时保留原动作条目 ID；新增动作不填写旧记录 ID')
    exercise_id: str | None = Field(default=None, description='上下文动作目录中的 ID，与 custom_name 二选一')
    custom_name: str | None = Field(default=None, min_length=1, max_length=100,
        description='目录无匹配动作时使用的用户动作名称；确认后创建自定义动作')
    weight_mode: Literal['external', 'bodyweight', 'added', 'assisted', 'unknown'] = Field(default='unknown',
        description='external 外部重量；bodyweight 自重；added 附加重量；assisted 辅助重量；不明确为 unknown')
    weight_scope: Literal['total', 'per_side', 'unknown'] = Field(default='unknown',
        description='total 总重量；per_side 单侧重量；不明确为 unknown')
    sets: list[ToolSetInput] = Field(min_length=1, max_length=100,
        description='按实际顺序逐组填写，至少一组；不将训练建议转换为已完成组')

    @model_validator(mode='after')
    def identity(self):
        if bool(self.exercise_id) == bool(self.custom_name):
            raise ValueError('Provide exercise_id or custom_name')
        return self


class ToolContent(Schema):
    """Model-facing workout content. Internal fields (confirm_create,
    missing_information) stay out of the schema; business validation reuses
    WorkoutContent after conversion."""

    actual_date: date = Field(description='训练实际发生日期，格式 YYYY-MM-DD，结合用户明确日期或选中日期填写；无法确定时询问')
    actual_time: time | None = Field(default=None, description='实际训练时间；用户未提供时为 null')
    notes: str = Field(default='', max_length=4000, description='整场训练的补充说明')
    exercises: list[ToolExerciseInput] = Field(min_length=1, max_length=100)

    def to_business(self):
        return WorkoutContent.model_validate(self.model_dump(mode='json'))


class SaveWorkout(Schema):
    content: ToolContent = Field(description='完整训练内容')
    workout_id: str | None = Field(default=None, description='修改时的原记录 ID，来自读取结果；新增时不填写')
    expected_version: int | None = Field(default=None, ge=1, description='修改时读取到的原记录当前版本；新增时不填写')

    @model_validator(mode='after')
    def target(self):
        if (self.workout_id is None) != (self.expected_version is None):
            raise ValueError('workout_id and expected_version must appear together for updates')
        return self


class DeleteWorkout(Schema):
    workout_id: str = Field(description='已明确指定的记录 ID')
    expected_version: int = Field(ge=1, description='读取到的记录当前版本，版本冲突后需重新读取与确认')


def _groups_text(sets):
    return '；'.join('{} kg × {} 次'.format(s['weight_kg'] if s['weight_kg'] is not None else '未记录',
        s['reps'] if s['reps'] is not None else '未记录') for s in sets)


def workout_summary(content):
    """Plain-Chinese summary used by confirmation cards and receipts."""
    lines = ['训练记录：' + content['actual_date'] + (' ' + content['actual_time'] if content.get('actual_time') else '')]
    for item in content['exercises']:
        name = item.get('name_snapshot') or item.get('custom_name') or '自定义动作'
        lines.append(name + '（' + item['weight_mode'] + ' / ' + item['weight_scope'] + '）')
        for i, group in enumerate(item['sets'], 1):
            lines.append('第{}组 · {} · {} kg × {} 次'.format(i, '热身' if group['kind'] == 'warmup' else '正式',
                group['weight_kg'] if group['weight_kg'] is not None else '未记录',
                group['reps'] if group['reps'] is not None else '未记录') + (' · ' + group['notes'] if group.get('notes') else ''))
    if content.get('notes'):
        lines.append('备注：' + content['notes'])
    return '\n'.join(lines)


def display_content(ctx, content):
    """Resolve catalog names so cards show real exercise names before saving."""
    from ...services import exercise
    resolved = {**content, 'exercises': []}
    for item in content['exercises']:
        if item.get('name_snapshot'):
            resolved['exercises'].append(item)
            continue
        name = item['custom_name'] or '自定义动作'
        if item.get('exercise_id'):
            name = exercise(ctx.db, item['exercise_id'], ctx.user_id).name
        resolved['exercises'].append({**item, 'name_snapshot': name})
    return resolved


def _target(ctx, workout_id, expected_version):
    original = owned(ctx.db, Workout, workout_id, ctx.user_id)
    if original.deleted_at:
        fail(409, 'workout_trashed')
    version(original, expected_version)
    return original


def list_workouts(ctx, params):
    offset, limit = (0, 1) if params.latest else (params.offset, params.limit)
    rows, total = query_workouts(ctx.db, ctx.user_id, start=params.start, end=params.end,
        exercise_id=params.exercise_id, offset=offset, limit=limit)
    items = []
    for row in rows:
        view = workout_view(ctx.db, row)
        items.append({'id': row.id, 'version': row.version,
            'summary': view['content']['actual_date'] + (' ' + view['content']['actual_time'] if view['content']['actual_time'] else '')
                + '：' + '；'.join((item.get('name_snapshot') or '') + '：' + _groups_text(item['sets']) for item in view['content']['exercises'])})
    has_more = offset + len(items) < total
    return {'items': items, 'total': total, 'has_more': has_more, 'next_offset': offset + len(items) if has_more else None}


def get_workout(ctx, params):
    return workout_view(ctx.db, owned(ctx.db, Workout, params.workout_id, ctx.user_id))


def validate_save(ctx, params):
    if ctx.mode == 'read':
        fail(422, 'read_only_turn')
    original = None
    if params.workout_id:
        original = _target(ctx, params.workout_id, params.expected_version)
    # Normalization only assigns stable IDs in memory; custom exercises are
    # created inside the confirmation transaction, never here.
    data = normalized_content(ctx.db, ctx.user_id, params.content.to_business())
    validate_exercise_references(ctx.db, ctx.user_id, data, original)
    return original


def execute_save(ctx, params):
    if ctx.mode == 'read':
        fail(422, 'read_only_turn')
    original = _target(ctx, params.workout_id, params.expected_version) if params.workout_id else None
    data = normalized_content(ctx.db, ctx.user_id, params.content.to_business())
    for item in data['exercises']:
        if item['custom_name']:
            # The user pressed confirm on a card disclosing custom creation.
            item['confirm_create'] = True
    workout = save_workout(ctx.db, ctx.user_id, data, original)
    view = workout_view(ctx.db, workout)
    return {'workout_id': workout.id, 'version': workout.version, 'summary': workout_summary(view['content'])}


def save_operation(payload):
    return 'update_workout' if payload.get('workout_id') else 'create_workout'


def save_summary(ctx, payload):
    label = '修改训练记录' if payload.get('workout_id') else '新增训练记录'
    return label + '\n' + workout_summary(display_content(ctx, payload['content']))


def save_details(ctx, payload):
    details = {'content': payload['content'], 'workout_id': payload.get('workout_id'),
               'expected_version': payload.get('expected_version'),
               'creating_custom': [item['custom_name'] for item in payload['content']['exercises'] if item['custom_name']]}
    if payload.get('workout_id'):
        # Before/after comparison so the user can verify the actual change.
        original = owned(ctx.db, Workout, payload['workout_id'], ctx.user_id)
        details['before'] = workout_view(ctx.db, original)['content']
        details['after'] = display_content(ctx, payload['content'])
    return details


def validate_delete(ctx, params):
    if ctx.mode == 'read':
        fail(422, 'read_only_turn')
    _target(ctx, params.workout_id, params.expected_version)


def execute_delete(ctx, params):
    if ctx.mode == 'read':
        fail(422, 'read_only_turn')
    return delete_workout(ctx.db, ctx.user_id, params.workout_id, params.expected_version)


def delete_summary(ctx, payload):
    original = owned(ctx.db, Workout, payload['workout_id'], ctx.user_id)
    view = workout_view(ctx.db, original)
    return '删除训练记录：{}（{} 个动作）'.format(view['content']['actual_date'], len(view['content']['exercises']))


def delete_details(ctx, payload):
    original = owned(ctx.db, Workout, payload['workout_id'], ctx.user_id)
    view = workout_view(ctx.db, original)
    return {'workout_id': payload['workout_id'], 'expected_version': payload['expected_version'],
            'actual_date': view['content']['actual_date'],
            'exercises': [item['name_snapshot'] for item in view['content']['exercises']]}


LIST_WORKOUTS = Tool(name='list_workouts',
    description='查询当前用户的真实训练记录。可按日期范围、动作筛选，或获取最近一次训练。结果包含记录摘要、ID、版本和分页信息。需要完整逐组内容时调用 get_workout；有下一页时可继续查询。只根据已返回的数据回答，空结果表示本次条件下未找到记录。',
    model=ListWorkouts, kind='read', execute=list_workouts)

GET_WORKOUT = Tool(name='get_workout',
    description='读取一条训练记录的完整内容和当前版本，用于查看详情或准备修改、删除。workout_id 使用查询结果或对话中明确指定的记录 ID。修改时基于返回内容保留未变更的信息与动作、组 ID；目标不明确时先询问用户。',
    model=GetWorkout, kind='read', execute=get_workout)

SAVE_WORKOUT = Tool(name='save_workout',
    description='新增或修改训练记录。content 为完整训练内容；修改时同时提供已读取的 workout_id 和 expected_version，并保留未变更信息及原动作、组 ID。新增时不填写原记录 ID 和版本。信息足够或用户要求跳过允许缺失的信息时调用。重量、次数可为 null，未知计重方式和口径使用 unknown；日期、可识别动作和至少一组记录是必填项。目录无匹配动作时使用 custom_name。工具会返回前端确认卡片，用户点击确认后才保存。',
    model=SaveWorkout, kind='write', validate=validate_save, execute=execute_save,
    operation=save_operation, summary=save_summary, details=save_details)

DELETE_WORKOUT = Tool(name='delete_workout',
    description='删除一条已明确指定的训练记录，传入已读取的 workout_id 和 expected_version。目标有歧义时先查询或询问。工具会返回前端确认卡片，用户点击确认后才删除。',
    model=DeleteWorkout, kind='write', validate=validate_delete, execute=execute_delete,
    operation=lambda payload: 'delete_workout', summary=delete_summary, details=delete_details)
