from helpers import write
from app.modules.profile import router as profile_router


def save_config(client, key='synthetic-user-key', version=1, status=200):
    return write(client, '/ai-config', {
        'base_url': 'https://user.example/v1', 'model': 'user-model', 'api_key': key, 'version': version,
    }, method='PUT', status=status)


def test_save_requires_passing_test(env, monkeypatch):
    _, (client, _) = env
    assert client.get('/api/ai-config').json() == {'configured': False}
    async def failing(*_):
        raise __import__('app.agent.provider', fromlist=['ProviderError']).ProviderError('model_auth_failed')
    monkeypatch.setattr(profile_router, 'test_connection', failing)
    body = save_config(client, status=502)
    assert body['detail']['code'] == 'model_auth_failed'
    assert client.get('/api/ai-config').json() == {'configured': False}

    async def passing(*_):
        return None
    monkeypatch.setattr(profile_router, 'test_connection', passing)
    saved = save_config(client)
    assert saved['configured'] is True and saved['has_api_key'] is True
    assert saved['model'] == 'user-model' and saved['base_url'] == 'https://user.example/v1'
    fetched = client.get('/api/ai-config').json()
    assert fetched == saved
    assert 'synthetic-user-key' not in client.get('/api/ai-config').text


def test_save_version_conflict_and_blank_key_reuse(env, monkeypatch):
    _, (client, _) = env
    async def passing(*_):
        return None
    monkeypatch.setattr(profile_router, 'test_connection', passing)
    saved = save_config(client, version=1)
    write(client, '/ai-config', {
        'base_url': 'https://changed.example/v1', 'model': 'next-model', 'version': saved['version'],
    }, method='PUT')
    refreshed = client.get('/api/ai-config').json()
    assert refreshed['has_api_key'] is True and refreshed['model'] == 'next-model'
    write(client, '/ai-config', {
        'base_url': 'https://changed.example/v1', 'model': 'next-model', 'version': saved['version'],
    }, method='PUT', status=409)


def test_test_endpoint_uses_stored_or_requires_key(env, monkeypatch):
    _, (client, _) = env
    seen = {}
    async def probe(key, model, base_url):
        seen.update(key=key, model=model, base_url=str(base_url))
    monkeypatch.setattr(profile_router, 'test_connection', probe)
    response = client.post('/api/ai-config/test', json={'base_url': 'https://x.example/v1', 'model': 'm'})
    assert response.status_code == 400
    assert response.json()['detail']['code'] == 'model_not_configured'
    save_config(client)
    response = client.post('/api/ai-config/test', json={'base_url': 'https://x.example/v1', 'model': 'm'})
    assert response.status_code == 200 and response.json() == {'ok': True}
    assert seen == {'key': 'synthetic-user-key', 'model': 'm', 'base_url': 'https://x.example/v1'}
    response = client.post('/api/ai-config/test', json={'base_url': 'https://x.example/v1', 'model': 'm', 'api_key': 'fresh'})
    assert response.status_code == 200
    assert seen['key'] == 'fresh'
