from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from app.errors import error_message
from app.agent.turns import turn_view


def test_backend_error_contract(env):
    _, (client, _) = env
    response = client.post('/api/auth/login', json={'username': 'alice', 'password': 'wrong-password'})
    assert response.status_code == 401
    assert response.json()['detail']['message'] == error_message('invalid_credentials')
    response = client.post('/api/auth/register', json={'username': '', 'password': 'private-secret'})
    assert response.status_code == 422
    detail = response.json()['detail']
    assert detail['code'] == 'validation_error'
    assert detail['message']
    assert detail['errors'][0]['loc']
    assert 'private-secret' not in response.text
    assert 'input' not in response.text
    assert client.get('/api/missing-endpoint').json()['detail']['message'] == error_message('not_found')

    @client.app.get('/test-busy')
    def busy():
        raise OperationalError('private-query', {}, Exception('database is locked'))

    response = client.get('/test-busy')
    assert response.status_code == 503
    assert response.headers['retry-after'] == '1'
    assert response.json()['detail']['retryable'] is True
    assert response.json()['detail']['message'] == error_message('database_busy')
    assert 'private-query' not in response.text

    @client.app.get('/test-unexpected')
    def unexpected():
        raise RuntimeError('private-secret')

    with TestClient(client.app, raise_server_exceptions=False) as safe_client:
        response = safe_client.get('/test-unexpected')
        assert response.status_code == 500
        assert response.json()['detail']['code'] == 'internal_error'
        assert 'private-secret' not in response.text


def test_turn_error_message():
    row = SimpleNamespace(id='turn', conversation_id='chat', status='failed',
                          error='model_timeout', result=None, created_at=1, context={})
    view = turn_view(row)
    assert view['error'] == 'model_timeout'
    assert view['error_message'] == error_message('model_timeout')
