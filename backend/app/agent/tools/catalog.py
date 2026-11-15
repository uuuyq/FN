"""Catalog tools: exercise availability preferences and user equipment."""
from ...models import Equipment
from ...schemas import PreferenceBatch, EquipmentInput
from ...services import exercise, version, fail
from .registry import Tool, WriteSummary


class UpdatePreferences(WriteSummary, PreferenceBatch):
    pass


class AddEquipment(WriteSummary, EquipmentInput):
    pass


def validate_preferences(ctx, params):
    if len({item.exercise_id for item in params.items}) != len(params.items):
        fail(422, 'duplicate_exercise')
    for item in params.items:
        from ...modules.catalog.service import get_preference
        row = exercise(ctx.db, item.exercise_id, ctx.user_id)
        pref = get_preference(ctx.db, ctx.user_id, row)
        if pref is None:
            if item.version != 1:
                fail(409, 'version_conflict', latest_version=1)
        else:
            version(pref, item.version)


def execute_preferences(ctx, params):
    from ...modules.catalog.service import update_preferences
    return update_preferences(ctx.db, ctx.user_id, PreferenceBatch.model_validate(params.model_dump(exclude={"summary"})))


def preferences_summary(ctx, payload):
    parts = []
    for item in payload['items']:
        name = exercise(ctx.db, item['exercise_id'], ctx.user_id).name
        parts.append('{} → {}'.format(name, '可用' if item['active'] else '不可用'))
    return '更新动作可用偏好：' + '、'.join(parts)


def preferences_details(ctx, payload):
    return {'items': payload['items']}


def validate_equipment(ctx, params):
    if params.equipment_id and not ctx.db.get(Equipment, params.equipment_id):
        fail(404, 'equipment_not_found')


def execute_equipment(ctx, params):
    from ...modules.catalog.service import add_equipment
    return add_equipment(ctx.db, ctx.user_id, EquipmentInput.model_validate(params.model_dump(exclude={"summary"})))


def equipment_summary(ctx, payload):
    return '新增可用器械：' + payload['name']


def equipment_details(ctx, payload):
    return {'name': payload['name'], 'equipment_id': payload.get('equipment_id')}


UPDATE_PREFERENCES = Tool(name='update_preferences',
    description='批量更新指定动作的可用偏好。每项使用 exercise_id、active 和偏好版本 version，返回更新后的偏好。',
    model=UpdatePreferences, kind='write', execution='user_confirmation', validate=validate_preferences, execute=execute_preferences,
    operation=lambda payload: 'update_preferences', summary=preferences_summary, details=preferences_details)

ADD_EQUIPMENT = Tool(name='add_equipment',
    description='新增用户可用器械，包含名称和可选的公共器械引用 equipment_id，返回新增器械。',
    model=AddEquipment, kind='write', execution='user_confirmation', validate=validate_equipment, execute=execute_equipment,
    operation=lambda payload: 'add_equipment', summary=equipment_summary, details=equipment_details)
