"""Authenticated encryption for user-provided model credentials."""
import os
import subprocess
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

FIELD = 'api_key_encrypted_v1'


def key_path():
    default = Path(__file__).resolve().parents[3] / 'runtime/secrets/ai-config.key'
    return Path(os.getenv('FNOTE_AI_KEY_FILE', str(default)))


def cipher(create=False):
    path = key_path()
    if create and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name == 'nt':
            sid = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], text=True).strip().split(',')[-1].strip('"')
            result = subprocess.run(['icacls', str(path.parent), '/inheritance:r', '/grant:r',
                                     f'*{sid}:(OI)(CI)F', '*S-1-5-18:(OI)(CI)F',
                                     '*S-1-5-32-544:(OI)(CI)F'], capture_output=True)
            if result.returncode:
                raise RuntimeError('Cannot secure AI key directory permissions')
        try:
            with path.open('xb') as stream:
                os.chmod(path, 0o600)
                stream.write(Fernet.generate_key())
        except FileExistsError:
            pass
    try:
        return Fernet(path.read_bytes().strip())
    except (OSError, ValueError):
        raise RuntimeError('AI credential key file is missing or invalid') from None


def decrypt_config(config):
    config = dict(config or {})
    if FIELD in config:
        try:
            config['api_key'] = cipher().decrypt(config.pop(FIELD).encode()).decode()
        except (InvalidToken, ValueError, UnicodeError):
            raise RuntimeError('AI credential cannot be decrypted with this key file') from None
    elif config.get('api_key'):
        raise RuntimeError('AI credentials require migration; run scripts.local prepare')
    return config


def encrypt_config(config):
    config = dict(config)
    key = config.pop('api_key', None)
    if key:
        config[FIELD] = cipher().encrypt(key.encode()).decode()
    return config


def migrate_credentials(engine):
    from ..models import User
    with Session(engine) as db, db.begin():
        users = db.scalars(select(User)).all()
        # Validate every existing ciphertext before creating a new master key.
        for user in users:
            if FIELD in (user.ai_config or {}):
                decrypt_config(user.ai_config)
        cipher(create=True)
        for user in users:
            if (user.ai_config or {}).get('api_key'):
                user.ai_config = encrypt_config(user.ai_config)
