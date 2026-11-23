from helpers import write
from app.modules.profile import router as profile_router


def save_config(client, key='synthetic-user-key', version=1, status=200):
    return write(client, '/ai-config', {
        'base_url': 'https://user.example/v1', 'model': 'user-model', 'api_key': key, 'version': version,
    }, method='PUT', status=status)


def test_save_requires_passing_test(env, monkeypatch):
    _, (client, _) = env
    assert client.get('/api/ai-config').json() == {'configured': False, 'setup_dismissed': False}
    async def failing(*_):
        raise __import__('app.agent.provider', fromlist=['ProviderError']).ProviderError('model_auth_failed')
    monkeypatch.setattr(profile_router, 'test_connection', failing)
    body = save_config(client, status=502)
    assert body['detail']['code'] == 'model_auth_failed'
    assert client.get('/api/ai-config').json() == {'configured': False, 'setup_dismissed': False}

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
        'base_url': 'https://user.example/v1', 'model': 'next-model', 'version': saved['version'],
    }, method='PUT')
    refreshed = client.get('/api/ai-config').json()
    assert refreshed['has_api_key'] is True and refreshed['model'] == 'next-model'
    write(client, '/ai-config', {
        'base_url': 'https://user.example/v1', 'model': 'next-model', 'version': saved['version'],
    }, method='PUT', status=409)


def test_test_endpoint_uses_stored_or_requires_key(env, monkeypatch):
    _, (client, _) = env
    seen = {}
    async def probe(key, model, base_url, effort):
        assert effort == 'default'
        seen.update(key=key, model=model, base_url=str(base_url))
    monkeypatch.setattr(profile_router, 'test_connection', probe)
    response = client.post('/api/ai-config/test', json={'base_url': 'https://user.example/v1', 'model': 'm'})
    assert response.status_code == 400
    assert response.json()['detail']['code'] == 'model_not_configured'
    save_config(client)
    response = client.post('/api/ai-config/test', json={'base_url': 'https://user.example/v1', 'model': 'm'})
    assert response.status_code == 200 and response.json() == {'ok': True}
    assert seen == {'key': 'synthetic-user-key', 'model': 'm', 'base_url': 'https://user.example/v1'}
    response = client.post('/api/ai-config/test', json={'base_url': 'https://user.example/v1', 'model': 'm', 'api_key': 'fresh'})
    assert response.status_code == 200
    assert seen['key'] == 'fresh'


def test_reasoning_settings(env, monkeypatch):
    _, (client, _) = env
    async def passing(*args):
        assert args[-1] == 'low'
    monkeypatch.setattr(profile_router, 'test_connection', passing)
    body = {'base_url': 'https://api.deepseek.com', 'model': 'deepseek-flash',
            'api_key': 'synthetic', 'version': 1, 'reasoning_effort': 'low'}
    saved = write(client, '/ai-config', body, method='PUT')
    assert saved['reasoning_effort'] == 'low'
    assert client.get('/api/ai-config').json()['reasoning_effort'] == 'low'
    body['reasoning_effort'] = 'invalid'
    write(client, '/ai-config', body, method='PUT', status=422)


def test_reasoning_parameters(monkeypatch):
    from app.agent.provider import reasoning_parameters
    monkeypatch.setenv('AI_REASONING_EFFORT', 'low')
    assert reasoning_parameters('https://api.deepseek.com') == {}
    assert reasoning_parameters('https://api.deepseek.com', 'none') == {
        'reasoning_effort': 'none', 'thinking': {'type': 'disabled'}}
    assert reasoning_parameters('https://example.com/v1', 'max') == {'reasoning_effort': 'max'}


def test_changed_target_requires_key_and_preserves_config(env, monkeypatch):
    _, (client, other) = env
    async def passing(*args):
        return None
    monkeypatch.setattr(profile_router, 'test_connection', passing)
    saved = save_config(client)
    write(client, '/ai-config', {
        'base_url': 'https://new.example/v1', 'model': 'm', 'version': saved['version'],
    }, method='PUT', status=400)
    assert client.get('/api/ai-config').json() == saved
    assert other.get('/api/ai-config').json()['configured'] is False
    async def failing(*args):
        from app.agent.provider import ProviderError
        raise ProviderError('model_auth_failed')
    monkeypatch.setattr(profile_router, 'test_connection', failing)
    save_config(client, key='bad', version=saved['version'], status=502)
    assert client.get('/api/ai-config').json() == saved


def test_presets_and_persistent_dismissal(env):
    _, (client, _) = env
    assert {p['id'] for p in client.get('/api/ai-config/presets').json()} == {'deepseek', 'kimi', 'qwen', 'openai'}
    write(client, '/ai-config/dismiss', {}, method='POST')
    assert client.get('/api/ai-config').json() == {'configured': False, 'setup_dismissed': True}


def test_provider_specific_payload_parameters():
    from app.agent.provider import completion_parameters
    assert completion_parameters('https://api.moonshot.cn/v1', 'none', 16000) == {
        'thinking': {'type': 'disabled'}, 'max_tokens': 16000}
    assert completion_parameters('https://dashscope.aliyuncs.com/compatible-mode/v1', 'high', 16000) == {
        'enable_thinking': True, 'max_tokens': 16000}
    assert completion_parameters('https://api.openai.com/v1', 'medium', 16000) == {
        'reasoning_effort': 'medium', 'max_completion_tokens': 16000}
    assert completion_parameters('https://custom.example/v1', 'default', 16000) == {'max_tokens': 16000}
