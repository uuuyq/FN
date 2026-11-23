from .service import update_profile
from ...core.credentials import FIELD, decrypt_config, encrypt_config

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from ...agent.presets import PRESETS, infer_provider
from ...agent.provider import ProviderError, test_connection
from ...models import User
from ...schemas import AiConfigSave, AiConfigTest, Profile
from ...services import fail, version
from typing import Annotated


RequestId = Annotated[str, Header(alias="X-Request-ID", min_length=8, max_length=100)]


def ai_config_view(user):
    config = user.ai_config or {}
    if not config.get(FIELD):
        return {'configured': False, 'setup_dismissed': bool(config.get('setup_dismissed')), **({'version': user.ai_config_version} if config.get('model') else {}), **{k: config[k] for k in ('provider', 'model', 'base_url', 'reasoning_effort') if k in config}}
    return {'configured': True, 'provider': config.get('provider', infer_provider(config)), 'version': user.ai_config_version, 'model': config['model'],
            'reasoning_effort': config.get('reasoning_effort', 'high'), 'base_url': config['base_url'], 'has_api_key': bool(config.get(FIELD))}


def register(app, engine, identity, mutate, secure, password_hasher, dummy_hash):
    @app.get('/api/profile')
    def get_profile(user_id=Depends(identity)):
        with Session(engine) as db:
            user = db.get(User, user_id)
            return Profile(version=user.profile_version, **user.profile).model_dump()

    @app.put('/api/profile')
    def put_profile(body: Profile, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            return update_profile(db, user_id, body)
        return mutate(request, user_id, x_request_id, body, action)

    @app.get('/api/ai-config')
    def get_ai_config(user_id=Depends(identity)):
        with Session(engine) as db:
            return ai_config_view(db.get(User, user_id))

    @app.get('/api/ai-config/presets')
    def get_presets(user_id=Depends(identity)):
        return PRESETS

    @app.post('/api/ai-config/dismiss')
    def dismiss_setup(request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            user = db.get(User, user_id)
            user.ai_config = {**(user.ai_config or {}), 'setup_dismissed': True}
            return ai_config_view(user)
        return mutate(request, user_id, x_request_id, {}, action)

    def resolve_key(db, user_id, body):
        if body.api_key:
            return body.api_key
        config = db.get(User, user_id).ai_config or {}
        same_target = str(body.base_url).rstrip('/') == str(config.get('base_url', '')).rstrip('/')
        stored = decrypt_config(config).get('api_key') if same_target and body.provider == config.get('provider', infer_provider(config)) else None
        if not stored:
            fail(400, 'model_not_configured')
        return stored

    async def probe(db, user_id, body):
        candidate = body.model_dump(exclude={'version'})
        candidate['base_url'] = str(body.base_url).rstrip('/')
        candidate['api_key'] = resolve_key(db, user_id, body)
        if body.provider != 'custom':
            preset = next(p for p in PRESETS if p['id'] == body.provider)
            if candidate['base_url'] != preset['base_url'] or body.model not in preset['models'] or body.reasoning_effort not in ['default', *preset['efforts']]:
                fail(400, 'model_config_invalid')
        try:
            await test_connection(candidate['api_key'], body.model, body.base_url, body.reasoning_effort)
        except ProviderError as error:
            fail(502, str(error))
        return candidate

    @app.post('/api/ai-config/test')
    async def post_ai_config_test(body: AiConfigTest, user_id=Depends(identity)):
        with Session(engine) as db:
            await probe(db, user_id, body)
        return {'ok': True}

    @app.put('/api/ai-config')
    async def put_ai_config(body: AiConfigSave, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        with Session(engine) as db:
            candidate = await probe(db, user_id, body)

        def action(db):
            user = db.get(User, user_id)
            version(user, body.version, 'ai_config_version')
            user.ai_config = encrypt_config(candidate)
            user.ai_config_version += 1
            return ai_config_view(user)
        return mutate(request, user_id, x_request_id, body, action)


    @app.delete('/api/ai-config')
    def delete_ai_key(request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        def action(db):
            user = db.get(User, user_id)
            user.ai_config = {k: v for k, v in (user.ai_config or {}).items() if k not in (FIELD, 'api_key')}
            user.ai_config_version += 1
            return ai_config_view(user)
        return mutate(request, user_id, x_request_id, {}, action)
