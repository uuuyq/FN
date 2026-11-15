"""Profile tool. Proposes a full-profile update confirmed by button."""
from ...models import User
from ...schemas import Profile
from ...services import version
from .registry import Tool, WriteSummary


class UpdateProfile(WriteSummary, Profile):
    pass


_FIELDS = {'goal': '目标', 'days_per_week': '每周训练天数', 'minutes_per_session': '单次时长',
           'preferences': '偏好', 'restrictions': '限制', 'timezone': '时区'}


def validate_update(ctx, params):
    version(ctx.db.get(User, ctx.user_id), params.version, 'profile_version')


def execute_update(ctx, params):
    from ...modules.profile.service import update_profile
    return update_profile(ctx.db, ctx.user_id, Profile.model_validate(params.model_dump(exclude={"summary"})))


def update_summary(ctx, payload):
    user = ctx.db.get(User, ctx.user_id)
    current = Profile(version=user.profile_version, **(user.profile or {})).model_dump(exclude={'version'})
    changed = [label for field, label in _FIELDS.items() if payload.get(field) != current.get(field)]
    return '更新个人条件' + (('：' + '、'.join(changed)) if changed else '')


def update_details(ctx, payload):
    user = ctx.db.get(User, ctx.user_id)
    current = Profile(version=user.profile_version, **(user.profile or {})).model_dump(exclude={'version'})
    return {'before': current, 'after': {key: value for key, value in payload.items() if key != 'version'},
            'version': payload['version']}


UPDATE_PROFILE = Tool(name='update_profile',
    description='完整更新用户个人条件，使用 version 校验当前资料版本，返回更新后的资料。',
    model=UpdateProfile, kind='write', execution='user_confirmation', validate=validate_update, execute=execute_update,
    operation=lambda payload: 'update_profile', summary=update_summary, details=update_details)
