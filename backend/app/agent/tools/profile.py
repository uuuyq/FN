"""Profile tool. Proposes a partial profile update confirmed by button."""
from ...models import User
from ...schemas import Profile, Schema
from ...services import version
from .registry import Tool, WriteSummary


class UpdateProfile(WriteSummary, Profile):
    pass


_FIELDS = {
    'days_per_week': '每周训练天数', 'minutes_per_session': '单次时长',
    'preferences': '个人偏好', 'training_principles': '训练指导原则',
    'history_workout_count': '参考训练次数', 'timezone': '时区',
}


def validate_update(ctx, params):
    version(ctx.db.get(User, ctx.user_id), params.version, 'profile_version')


def execute_update(ctx, params):
    from ...modules.profile.service import update_profile
    current = get_profile(ctx, None)
    changes = params.model_dump(exclude={'summary'}, exclude_unset=True)
    return update_profile(ctx.db, ctx.user_id, Profile.model_validate({**current, **changes}))


def update_summary(ctx, payload):
    user = ctx.db.get(User, ctx.user_id)
    current = Profile(version=user.profile_version, **(user.profile or {})).model_dump(exclude={'version'})
    changed = [label for field, label in _FIELDS.items() if field in payload and payload[field] != current.get(field)]
    return '更新个人条件' + (('：' + '、'.join(changed)) if changed else '')


def update_details(ctx, payload):
    user = ctx.db.get(User, ctx.user_id)
    current = Profile(version=user.profile_version, **(user.profile or {})).model_dump(exclude={'version'})
    return {'before': current, 'after': {**current, **{key: value for key, value in payload.items() if key in _FIELDS}},
            'version': payload['version']}


UPDATE_PROFILE = Tool(name='update_profile',
    description='用户明确要求保存个人条件时，先调用 get_profile 读取资料和版本，再提交需要修改的字段。省略字段保留原值；days_per_week 和 minutes_per_session 显式传 null 表示清空。使用 version 校验版本。',
    model=UpdateProfile, kind='write', execution='user_confirmation', validate=validate_update, execute=execute_update,
    operation=lambda payload: 'update_profile', summary=update_summary, details=update_details)


class GetProfile(Schema):
    pass


def get_profile(ctx, params):
    user = ctx.db.get(User, ctx.user_id)
    return Profile(version=user.profile_version, **(user.profile or {})).model_dump(mode='json')


GET_PROFILE = Tool(name='get_profile', description='读取完整个人条件和当前版本，修改个人条件前调用。',
    model=GetProfile, kind='read', execution='direct', execute=get_profile)
