import pytest
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session
from app.core.credentials import FIELD, decrypt_config, encrypt_config, key_path, migrate_credentials
from app.models import User
from helpers import write


def test_encryption_and_wrong_key():
    stored = encrypt_config({'api_key': 'synthetic-secret'})
    assert 'api_key' not in stored
    assert 'synthetic-secret' not in str(stored)
    assert decrypt_config(stored)['api_key'] == 'synthetic-secret'
    key_path().write_bytes(Fernet.generate_key())
    with pytest.raises(RuntimeError, match='cannot be decrypted'):
        decrypt_config(stored)


def test_migration_and_delete(env):
    engine, (client, other) = env
    with Session(engine) as db, db.begin():
        user = db.query(User).filter_by(username='alice').one()
        user.ai_config = {'api_key': 'synthetic-secret', 'model': 'm', 'base_url': 'https://example.test/v1'}
        user_id = user.id
    migrate_credentials(engine)
    migrate_credentials(engine)
    with Session(engine) as db:
        stored = db.get(User, user_id).ai_config
        assert FIELD in stored and 'api_key' not in stored
    from app.agent.runner import _user_config
    assert _user_config(engine, user_id)['api_key'] == 'synthetic-secret'
    result = write(client, '/ai-config', {}, method='DELETE')
    assert result['configured'] is False
    assert result['model'] == 'm'
    assert other.get('/api/ai-config').json()['configured'] is False


def test_missing_master_key_does_not_regenerate(env):
    engine, _ = env
    with Session(engine) as db, db.begin():
        user = db.query(User).filter_by(username='alice').one()
        user.ai_config = encrypt_config({'api_key': 'synthetic-secret'})
    key_path().unlink()
    with pytest.raises(RuntimeError, match='missing or invalid'):
        migrate_credentials(engine)
    assert not key_path().exists()
