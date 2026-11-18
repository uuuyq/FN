"""Catalog tools: exercise availability preferences and user equipment."""
from ...models import Equipment, UserExercise, normalize_exercise_text
from sqlalchemy import select
from ...schemas import PreferenceBatch, EquipmentInput, ExerciseInput
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


class AddExercise(WriteSummary, ExerciseInput):
    pass


def validate_exercise(ctx, params):
    existing = ctx.db.scalar(select(UserExercise.id).where(
        UserExercise.user_id == ctx.user_id,
        UserExercise.normalized_name == normalize_exercise_text(params.name)))
    if existing:
        fail(409, 'exercise_name_taken')


def execute_exercise(ctx, params):
    from ...modules.catalog.service import create_exercise, catalog_view
    body = ExerciseInput.model_validate(params.model_dump(exclude={'summary'}))
    row = create_exercise(ctx.db, ctx.user_id, body)
    return {**catalog_view(ctx.db, row, ctx.user_id), 'summary': '已新增个人动作：' + row.name}


def exercise_summary(ctx, payload):
    return '新增个人动作：' + payload['name']


def exercise_details(ctx, payload):
    return {key: value for key, value in payload.items() if key != 'summary'}


ADD_EXERCISE = Tool(name='add_exercise',
    description='新增个人动作并默认加入选择动作。用户只要求新增动作时使用本工具。动作名称必填，training_parts 为训练部位数组，可选胸、背、腿、二头、三头、肩、腹。根据明确动作提供分类，不明确时先询问，分类随卡片确认。其余字段可选。可根据用户提供的动作补充别名、肌群、器械和说明，全部内容交由用户在卡片中确认；动作有歧义时先澄清。返回新增动作，不创建训练记录。',
    model=AddExercise, kind='write', execution='user_confirmation', validate=validate_exercise,
    execute=execute_exercise, operation=lambda payload: 'add_exercise',
    summary=exercise_summary, details=exercise_details)
