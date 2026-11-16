import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

from argon2 import PasswordHasher
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
import pytest

from app.core.database import write_transaction
from app.models import RequestReceipt, User
from app.modules.auth.limiter import AuthLimiter


def test_auth_limit_and_recovery(env):
    _, (client, _) = env
    limiter = client.app.state.auth_limiter
    clock = [100.0]
    limiter.clock = lambda: clock[0]
    limiter.buckets.clear()
    body = {'username': 'alice', 'password': 'incorrect'}
    for _ in range(10):
        assert client.post('/api/auth/login', json=body).status_code == 401
    response = client.post('/api/auth/login', json=body)
    assert response.status_code == 429
    assert response.headers['retry-after'] == '60'
    assert response.json()['detail']['code'] == 'auth_rate_limited'
    clock[0] += 60
    assert client.post('/api/auth/login', json=body).status_code == 401


def test_source_and_global_limits():
    request = SimpleNamespace(client=SimpleNamespace(host='source'))
    limiter = AuthLimiter(clock=lambda: 0)
    for index in range(30):
        limiter.check(request, str(index))
    with pytest.raises(HTTPException) as error:
        limiter.check(request, 'another-account')
    assert error.value.status_code == 429
    limiter = AuthLimiter(clock=lambda: 0)
    for index in range(300):
        request.client.host = str(index)
        limiter.check(request, str(index))
    with pytest.raises(HTTPException):
        request.client.host = 'new-source'
        limiter.check(request, 'new-account')


def test_account_receipt_uses_salted_argon2_and_replays(env):
    engine, (client, _) = env
    body = {'current_password': 'test-password-123', 'username': 'alice-renamed'}
    request_id = str(uuid4())
    headers = {'X-Request-ID': request_id}
    first = client.put('/api/auth/account', json=body, headers=headers)
    assert first.status_code == 200
    assert client.put('/api/auth/account', json=body, headers=headers).json() == first.json()
    with Session(engine) as db:
        receipt = db.scalar(select(RequestReceipt).where(RequestReceipt.request_id == request_id))
        payload = json.dumps(['PUT /api/auth/account', {**body, 'password': None}], sort_keys=True, ensure_ascii=False)
        assert PasswordHasher().verify(receipt.fingerprint, payload)
    changed = client.put('/api/auth/account', json={**body, 'username': 'different'}, headers=headers)
    assert changed.status_code == 409


@pytest.mark.parametrize('operation', ['login', 'account'])
def test_hashing_releases_database_and_rechecks_changed_password(env, test_hasher, monkeypatch, operation):
    engine, (client, _) = env
    original_verify = test_hasher.verify
    changed = False

    def verify(self, hashed, password):
        nonlocal changed
        result = original_verify(hashed, password)
        if not changed:
            changed = True
            # This independent writer must succeed during password verification.
            with write_transaction(engine) as db:
                user = db.scalar(select(User).where(User.username == 'alice'))
                user.password_hash = test_hasher.hash('replacement-password')
        return result

    monkeypatch.setattr(PasswordHasher, 'verify', verify)
    if operation == 'login':
        response = client.post('/api/auth/login', json={'username': 'alice', 'password': 'test-password-123'})
    else:
        response = client.put('/api/auth/account', json={
            'current_password': 'test-password-123', 'username': 'must-not-change',
        }, headers={'X-Request-ID': str(uuid4())})
    assert response.status_code == 401


def test_account_hashing_is_outside_write_transaction(env, test_hasher, monkeypatch):
    engine, (client, _) = env
    original_hash, original_verify = test_hasher.hash, test_hasher.verify

    def probe():
        with write_transaction(engine) as db:
            db.connection().exec_driver_sql('UPDATE users SET username = username')

    def hash_password(self, password):
        probe()
        return original_hash(password)

    def verify_password(self, hashed, password):
        probe()
        return original_verify(hashed, password)

    monkeypatch.setattr(PasswordHasher, 'hash', hash_password)
    monkeypatch.setattr(PasswordHasher, 'verify', verify_password)
    response = client.put('/api/auth/account', json={
        'current_password': 'test-password-123', 'password': 'replacement-password',
    }, headers={'X-Request-ID': str(uuid4())})
    assert response.status_code == 200
    assert client.get('/api/auth/me').status_code == 401


def test_account_concurrent_retry(env):
    engine, (client, _) = env
    request_id = str(uuid4())

    def rename(_):
        return client.put('/api/auth/account', json={
            'current_password': 'test-password-123', 'username': 'alice-renamed',
        }, headers={'X-Request-ID': request_id})

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(rename, range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    with Session(engine) as db:
        assert len(list(db.scalars(select(RequestReceipt).where(RequestReceipt.request_id == request_id)))) == 1


def test_legacy_account_receipt_tombstone_rejects_replay(env):
    engine, (client, _) = env
    user_id = client.get('/api/auth/me').json()['id']
    legacy_id, other_id = str(uuid4()), str(uuid4())
    with write_transaction(engine) as db:
        db.add_all([
            RequestReceipt(user_id=user_id, request_id=legacy_id, fingerprint='account-legacy',
                           result={'id': user_id, 'username': 'alice', 'login_required': False}),
            RequestReceipt(user_id=user_id, request_id=other_id, fingerprint='ordinary-digest',
                           result={'items': []}),
        ])
    with Session(engine) as db:
        assert db.get(RequestReceipt, (user_id, legacy_id)).fingerprint == 'account-legacy'
        assert db.get(RequestReceipt, (user_id, other_id)).fingerprint == 'ordinary-digest'
    response = client.put('/api/auth/account', json={
        'current_password': 'test-password-123', 'username': 'alice',
    }, headers={'X-Request-ID': legacy_id})
    assert response.status_code == 409


@pytest.mark.parametrize('operation', ['register', 'account'])
def test_limits_precede_expensive_hashing(env, monkeypatch, operation):
    _, (client, _) = env
    limiter = client.app.state.auth_limiter
    limiter.buckets.clear()
    for _ in range(30):
        limiter.check(SimpleNamespace(client=SimpleNamespace(host='testclient')), str(uuid4()))

    def unexpected_hash(*args, **kwargs):
        pytest.fail('Rate-limited requests must not perform Argon2 work')

    monkeypatch.setattr(PasswordHasher, 'hash', unexpected_hash)
    monkeypatch.setattr(PasswordHasher, 'verify', unexpected_hash)
    if operation == 'register':
        response = client.post('/api/auth/register', json={
            'username': 'new-user', 'password': 'synthetic-password',
            'password_confirmation': 'synthetic-password',
        })
    else:
        response = client.put('/api/auth/account', json={
            'current_password': 'test-password-123', 'username': 'new-user',
        }, headers={'X-Request-ID': str(uuid4())})
    assert response.status_code == 429
