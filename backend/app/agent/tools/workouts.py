"""Workout tools. Write tools only validate and propose; execution runs on confirm."""
from datetime import date, time
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, model_validator

from ...schemas import Schema, WorkoutContent
from ...models import Workout
from ...services import fail, owned, version
from ...modules.workouts.service import (normalized_content, workout_view, save_workout, delete_workout,
    query_workouts, validate_exercise_references, sets_brief)
from .registry import Tool, WriteSummary


class ListWorkouts(Schema):
    on: date | None = Field(default=None, description='训练日期，与日期范围互斥')
    start_date: date | None = None
    end_date: date | None = None
    exercise_id: str | None = None

    @model_validator(mode='after')
    def query_range(self):
        if self.on and (self.start_date or self.end_date):
            raise ValueError('on cannot combine with date range')
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError('invalid date range')
        return self
    offset: int = Field(default=0, ge=0, description='分页偏移量')
    limit: int = Field(default=20, ge=1, le=50, description='每页数量')


class GetWorkout(Schema):
    workout_id: str = Field(description='训练记录 ID')


class ToolSetInput(Schema):
    id: str | None = Field(default=None, description='训练组稳定 ID；新组为 null')
    kind: Literal['working', 'warmup'] = Field(default='working',
        description='组类型，working 为正式组，warmup 为热身组，默认 working')
    weight_kg: Decimal | None = Field(default=None, ge=0, le=10000, decimal_places=3,
        description='公斤重量，十进制字符串，最多三位小数；未记录为 null，零与未记录不同')
    reps: int | None = Field(default=None, strict=True, ge=0, le=10000, description='本组次数，整数；未记录为 null')
    notes: str = Field(default='', max_length=2000, description='本组备注，如器械调整或助力方式')


class ToolExerciseInput(Schema):
    exercise_id: str | None = Field(default=None, description='上下文动作目录中的 ID，与 custom_name 二选一')
    custom_name: str | None = Field(default=None, min_length=1, max_length=100,
        description='新建个人动作的名称，与 exercise_id 二选一')
    sets: list[ToolSetInput] = Field(min_length=1, max_length=100,
        description='按实际训练顺序排列的组列表，1 至 100 组')

    @model_validator(mode='after')
    def identity(self):
        if bool(self.exercise_id) == bool(self.custom_name):
            raise ValueError('Provide exercise_id or custom_name')
        return self


class ToolContent(Schema):
    """Model-facing workout content. Internal fields (confirm_create,
    missing_information) stay out of the schema; business validation reuses
    WorkoutContent after conversion."""

    actual_date: date = Field(description='训练实际发生日期，格式 YYYY-MM-DD')
    actual_time: time | None = Field(default=None, description='实际训练时间，可为 null')
    notes: str = Field(default='', max_length=4000, description='整场训练的补充说明')
    exercises: list[ToolExerciseInput] = Field(min_length=1, max_length=100)

    def to_business(self):
        return WorkoutContent.model_validate(self.model_dump(mode='json'))


class SaveWorkout(WriteSummary, Schema):
    content: ToolContent = Field(description='完整训练内容')
    workout_id: str | None = Field(default=None, description='修改目标的训练记录 ID；新增记录为 null，与 expected_version 同时提供或同时为空')
    expected_version: int | None = Field(default=None, ge=1, description='修改目标的当前版本，正整数；新增记录为 null')
    allow_missing: list[Literal['reps', 'weight_kg']] = Field(default_factory=list, max_length=2,
        description='用户明确允许缺失的字段名列表，可选 reps、weight_kg，默认为空列表')
    assumptions: list[str] = Field(default_factory=list, max_length=10,
        description='已向用户说明的待核实假设列表，显示于确认详情，最多 10 项')

    @model_validator(mode='after')
    def target(self):
        if (self.workout_id is None) != (self.expected_version is None):
            raise ValueError('workout_id and expected_version must appear together for updates')
        return self


class DeleteWorkout(WriteSummary, Schema):
    workout_id: str = Field(description='待删除的训练记录 ID')
    expected_version: int = Field(ge=1, description='待删除记录的当前版本，正整数')


def workout_summary(content, assumptions=None):
    """Plain-Chinese summary used by confirmation cards and receipts.

    Consecutive identical sets aggregate into one clause; the full per-set
    detail stays available in the structured content.
    """
    lines = ['训练记录：' + content['actual_date'] + (' ' + content['actual_time'] if content.get('actual_time') else '')]
    for item in content['exercises']:
        name = item.get('name') or item.get('custom_name') or '自定义动作'
        brief = sets_brief(item['sets'])
        lines.append(name + (('：' + brief) if brief else ''))
    if assumptions:
        lines.append('待核实：' + '；'.join(assumptions))
    if content.get('notes'):
        lines.append('备注：' + content['notes'])
    return '\n'.join(lines)


def display_content(ctx, content):
    """Resolve catalog names so cards show real exercise names before saving."""
    from ...services import exercise
    resolved = {**content, 'exercises': []}
    for item in content['exercises']:
        if item.get('name'):
            resolved['exercises'].append(item)
            continue
        name = item.get('custom_name') or '自定义动作'
        if item.get('exercise_id'):
            name = exercise(ctx.db, item['exercise_id'], ctx.user_id).name
        resolved['exercises'].append({**item, 'name': name})
    return resolved


def _target(ctx, workout_id, expected_version):
    original = owned(ctx.db, Workout, workout_id, ctx.user_id)
    if original.deleted_at:
        fail(409, 'workout_trashed')
    version(original, expected_version)
    return original


def list_workouts(ctx, params):
    offset, limit = params.offset, params.limit
    rows, total = query_workouts(ctx.db, ctx.user_id, on=params.on, start_date=params.start_date, end_date=params.end_date, exercise_id=params.exercise_id, offset=offset, limit=limit)
    items = []
    for row in rows:
        view = workout_view(ctx.db, row)
        items.append({'id': row.id, 'version': row.version,
            'summary': view['content']['actual_date'] + (' ' + view['content']['actual_time'] if view['content']['actual_time'] else '')
                + '：' + '；'.join((item.get('name') or '') + ' ' + sets_brief(item['sets']) for item in view['content']['exercises'])})
    has_more = offset + len(items) < total
    return {'items': items, 'total': total, 'has_more': has_more, 'next_offset': offset + len(items) if has_more else None}


def get_workout(ctx, params):
    return workout_view(ctx.db, owned(ctx.db, Workout, params.workout_id, ctx.user_id))


def _exercise_label(ctx, item):
    if item.get('custom_name'):
        return item['custom_name']
    if item.get('exercise_id'):
        from ...services import exercise
        try:
            return exercise(ctx.db, item['exercise_id'], ctx.user_id).name
        except HTTPException:
            return item['exercise_id']
    return '未指定动作'


def _check_readiness(ctx, data, allow_missing):
    """Deterministic proposal readiness: critical fields present or explicitly skipped.

    Rejecting an early proposal returns a structured reason so the model asks
    the user instead; the UI stays without a card. Warmup sets are optional
    detail and exempt; only working sets carry the critical-content bar.
    """
    problems = []
    for item in data['exercises']:
        label = _exercise_label(ctx, item)
        working = [s for s in item['sets'] if s.get('kind', 'working') != 'warmup']
        if 'reps' not in allow_missing and any(s['reps'] is None for s in working):
            problems.append('{}：次数'.format(label))
    if problems:
        fail(422, 'missing_key_information', field='、'.join(problems))


def validate_save(ctx, params):
    if ctx.mode == 'read':
        fail(422, 'read_only_turn')
    original = None
    if params.workout_id:
        original = _target(ctx, params.workout_id, params.expected_version)
    # Normalization only assigns stable IDs in memory; custom exercises are
    # created inside the confirmation transaction, never here.
    data = normalized_content(ctx.db, ctx.user_id, params.content.to_business())
    validate_exercise_references(ctx.db, ctx.user_id, data)
    # New records must be complete or explicitly skipped; updates keep their
    # original values and only change requested fields.
    if original is None:
        _check_readiness(ctx, data, params.allow_missing)
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
    return label + '\n' + workout_summary(display_content(ctx, payload['content']), payload.get('assumptions'))


def save_details(ctx, payload):
    details = {'content': payload['content'], 'workout_id': payload.get('workout_id'),
               'expected_version': payload.get('expected_version'),
               'allow_missing': payload.get('allow_missing', []),
               'assumptions': payload.get('assumptions', []),
               'missing_fields': [field for field in ('weight_kg', 'reps') if any(group.get(field) is None for item in payload['content']['exercises'] for group in item['sets'])],
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
            'exercises': [item['name'] for item in view['content']['exercises']]}


LIST_WORKOUTS = Tool(name='list_workouts',
    description='按单日、日期范围或动作分页查询训练记录，无日期条件时查询最近记录，按训练日期倒序，返回记录摘要、ID、版本、总数及分页信息。',
    model=ListWorkouts, kind='read', execution='direct', execute=list_workouts)

GET_WORKOUT = Tool(name='get_workout',
    description='按 ID 读取当前用户的一条训练记录，返回完整训练内容、组 ID 和当前版本。',
    model=GetWorkout, kind='read', execution='direct', execute=get_workout)

SAVE_WORKOUT = Tool(name='save_workout',
    description='记录用户实际完成的训练，新增或完整替换一条训练记录。仅新增动作使用 add_exercise。修改使用记录 ID 和版本进行并发校验。支持同时创建个人动作，返回记录 ID、版本和摘要。',
    model=SaveWorkout, kind='write', execution='user_confirmation', validate=validate_save, execute=execute_save,
    operation=save_operation, summary=save_summary, details=save_details)

DELETE_WORKOUT = Tool(name='delete_workout',
    description='按记录 ID 和当前版本软删除一条训练记录。',
    model=DeleteWorkout, kind='write', execution='user_confirmation', validate=validate_delete, execute=execute_delete,
    operation=lambda payload: 'delete_workout', summary=delete_summary, details=delete_details)
