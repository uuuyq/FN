import sys
from pathlib import Path
import pytest
import sqlite3
from importlib import import_module
BACKEND = Path(__file__).resolve().parents[1] / 'backend'
sys.path.insert(0, str(BACKEND))

@pytest.fixture(autouse=True)
def backend_working_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("FNOTE_AI_KEY_FILE", str(tmp_path / "ai-config.key"))
    monkeypatch.chdir(BACKEND)
    from app.core.credentials import cipher
    cipher(create=True)


@pytest.fixture(scope='session')
def test_hasher():
    from argon2 import PasswordHasher
    # Test-only work factors: exercise real hashing without production CPU cost.
    return PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)


@pytest.fixture(scope='session')
def database_template(tmp_path_factory, test_hasher):
    from alembic import command
    from alembic.config import Config
    from app.core.database import make_engine, write_transaction
    from app.models import User
    from scripts.seed import seed
    path = tmp_path_factory.mktemp('template') / 'test.db'
    url = 'sqlite:///' + path.as_posix()
    config = Config(str(BACKEND / 'alembic.ini'))
    config.set_main_option('script_location', str(BACKEND / 'migrations'))
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('DATABASE_URL', url)
        command.upgrade(config, 'head')
    engine = make_engine(url)
    seed(engine)
    password = test_hasher.hash('test-password-123')
    with write_transaction(engine) as db:
        for username in ('alice', 'bob'):
            db.add(User(username=username, password_hash=password))
    engine.dispose()
    return path


@pytest.fixture
def env(tmp_path, monkeypatch, database_template, test_hasher):
    from fastapi.testclient import TestClient
    from app.core.database import make_engine
    from app.main import create_app
    path = tmp_path / 'test.db'
    with sqlite3.connect(database_template) as source, sqlite3.connect(path) as target:
        source.backup(target)
    url = 'sqlite:///' + path.as_posix()
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setenv('COOKIE_SECURE', 'false')
    monkeypatch.setattr(import_module('app.main'), 'PasswordHasher', lambda: test_hasher)
    engine = make_engine(url)
    app = create_app(engine)
    clients = []
    try:
        for username in ('alice', 'bob'):
            client = TestClient(app)
            clients.append(client)
            response = client.post('/api/auth/login', json={
                'username': username, 'password': 'test-password-123'})
            assert response.status_code == 200, response.text
            client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        yield engine, clients
    finally:
        for client in clients:
            client.close()
        engine.dispose()
