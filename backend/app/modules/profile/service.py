from ...models import User
from ...services import version


def update_profile(db, user_id, body):
    user = db.get(User, user_id)
    version(user, body.version, 'profile_version')
    user.profile = body.model_dump(exclude={'version'})
    user.profile_version += 1
    return {**user.profile, 'version': user.profile_version}
