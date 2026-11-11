"""Catalog tools: exercise availability preferences and user equipment."""
from ...models import Equipment, ExercisePreference
from ...schemas import PreferenceBatch, EquipmentInput
from ...services import exercise, version, fail
from .registry import Tool


class UpdatePreferences(PreferenceBatch):
    pass


class AddEquipment(EquipmentInput):
    pass


def validate_preferences(ctx, params):
    for item in params.items:
        exercise(ctx.db, item.exercise_id, ctx.user_id)
        pref = ctx.db.get(ExercisePreference, (ctx.user_id, item.exercise_id))
        version(pref or _default_pref(), item.version)


def _default_pref():
    from ...models import ExercisePreference as model
    return model(version=1)


def execute_preferences(ctx, params):
    from ...modules.catalog.service import update_preferences
    return update_preferences(ctx.db, ctx.user_id, params)


def preferences_summary(ctx, payload):
    parts = []
    for item in payload['items']:
        name = exercise(ctx.db, item['exercise_id'], ctx.user_id).name
        parts.append('{} → {}'.format(name, '可用' if item['available'] else '不可用'))
    return '更新动作可用偏好：' + '、'.join(parts)


def preferences_details(ctx, payload):
    return {'items': payload['items']}


def validate_equipment(ctx, params):
    if params.equipment_id and not ctx.db.get(Equipment, params.equipment_id):
        fail(404, 'equipment_not_found')


def execute_equipment(ctx, params):
    from ...modules.catalog.service import add_equipment
    return add_equipment(ctx.db, ctx.user_id, params)


def equipment_summary(ctx, payload):
    return '新增可用器械：' + payload['name']


def equipment_details(ctx, payload):
    return {'name': payload['name'], 'equipment_id': payload.get('equipment_id')}


UPDATE_PREFERENCES = Tool(name='update_preferences',
    description='更新用户的动作可用偏好。每项包含目录中的 exercise_id、目标 available 状态及 version（使用上下文的 preference_version），只提交需要变更的项目。工具会返回前端确认卡片，用户点击确认后才更新。',
    model=UpdatePreferences, kind='write', validate=validate_preferences, execute=execute_preferences,
    operation=lambda payload: 'update_preferences', summary=preferences_summary, details=preferences_details)

ADD_EQUIPMENT = Tool(name='add_equipment',
    description='为用户新增可用器械，提供名称；上下文存在对应公共器械 ID 时可一并提供。工具会返回前端确认卡片，用户点击确认后才新增。',
    model=AddEquipment, kind='write', validate=validate_equipment, execute=execute_equipment,
    operation=lambda payload: 'add_equipment', summary=equipment_summary, details=equipment_details)
