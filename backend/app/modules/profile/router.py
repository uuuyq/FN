from .service import update_profile

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from ...agent.provider import ProviderError, test_connection
from ...models import User
from ...schemas import AiConfigSave, AiConfigTest, Profile
from ...services import fail, version
from typing import Annotated


RequestId = Annotated[str, Header(alias="X-Request-ID", min_length=8, max_length=100)]


def ai_config_view(user):
    config = user.ai_config or {}
    if not all(config.get(field) for field in ('api_key', 'model', 'base_url')):
        return {'configured': False}
    return {'configured': True, 'version': user.ai_config_version, 'model': config['model'],
            'reasoning_effort': config.get('reasoning_effort', 'high'), 'base_url': config['base_url'], 'has_api_key': bool(config.get('api_key'))}


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

    def resolve_key(db, user_id, body):
        if body.api_key:
            return body.api_key
        stored = (db.get(User, user_id).ai_config or {}).get('api_key')
        if not stored:
            fail(400, 'model_not_configured')
        return stored

    async def probe(db, user_id, body):
        try:
            await test_connection(resolve_key(db, user_id, body), body.model, body.base_url, body.reasoning_effort)
        except ProviderError as error:
            fail(502, str(error))

    @app.post('/api/ai-config/test')
    async def post_ai_config_test(body: AiConfigTest, user_id=Depends(identity)):
        with Session(engine) as db:
            await probe(db, user_id, body)
        return {'ok': True}

    @app.put('/api/ai-config')
    async def put_ai_config(body: AiConfigSave, request: Request, x_request_id: RequestId, user_id=Depends(identity)):
        with Session(engine) as db:
            await probe(db, user_id, body)

        def action(db):
            user = db.get(User, user_id)
            version(user, body.version, 'ai_config_version')
            user.ai_config = {'api_key': resolve_key(db, user_id, body), 'model': body.model,
                              'base_url': str(body.base_url).rstrip('/'), 'reasoning_effort': body.reasoning_effort}
            user.ai_config_version += 1
            return ai_config_view(user)
        return mutate(request, user_id, x_request_id, body, action)

