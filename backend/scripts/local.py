"""Cross-platform single-process deployment and verified SQLite backups."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
import uuid
import re
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = Path(os.getenv('FNOTE_RUNTIME', str(ROOT / 'runtime'))).resolve()
DATABASE = Path(os.getenv('FNOTE_DATABASE', str(ROOT / 'backend/data/fnote.db'))).resolve()
BACKUPS = Path(os.getenv('FNOTE_BACKUPS', str(RUNTIME / 'backups'))).resolve()


def validate(path):
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Database integrity validation failed')
        db.execute('SELECT id FROM users LIMIT 1')
        return db.execute('SELECT version_num FROM alembic_version').fetchone()[0]


def backup(source=None, directory=None):
    source = Path(source or DATABASE).resolve(strict=True)
    directory = Path(directory or BACKUPS).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / ('fnote-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex + '.db')
    pending = destination.with_suffix('.partial')
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(pending)) as dst:
            src.backup(dst)
        validate(pending)
        pending.replace(destination)
    except BaseException:
        pending.unlink(missing_ok=True)
        raise
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    for candidate in directory.iterdir():
        match = re.fullmatch(r'fnote-(\d{8}T\d{6}Z)-[0-9a-f]{32}\.db', candidate.name)
        if match and candidate.is_file() and not candidate.is_symlink():
            try:
                created = datetime.strptime(match[1], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if created < cutoff:
                candidate.unlink()
    return destination


@contextmanager
def exclusive(directory=None):
    """OS releases the lock on normal exit or crash; stale PID files don't lock."""
    if os.name == 'nt':
        import msvcrt
    else:
        import fcntl
    directory = Path(directory or RUNTIME)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'instance.lock').open('a+b') as handle:
        try:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise RuntimeError('FNote is running; stop it before migration or restore') from None
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def restore(source, destination=None, backup_directory=None):
    source, destination = Path(source).resolve(strict=True), Path(destination or DATABASE).resolve()
    validate(source)
    if source == destination:
        raise RuntimeError('Source and destination must differ')
    # Caller must hold exclusive lock and stop all writers. Preserve current DB.
    previous = backup(destination, backup_directory) if destination.exists() else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(destination)) as dst:
        src.backup(dst)
    validate(destination)
    return previous


def prepare():
    from alembic import command
    from alembic.config import Config
    from app.core.database import make_engine
    from scripts.seed import seed
    with exclusive():
        previous = backup() if DATABASE.exists() else None
        if previous:
            print('Pre-upgrade backup:', previous)
        try:
            command.upgrade(Config('alembic.ini'), 'head')
            engine = make_engine()
            try:
                seed(engine)
            finally:
                engine.dispose()
            command.check(Config('alembic.ini'))
            validate(DATABASE)
            from app.core.credentials import migrate_credentials
            migration_engine = make_engine()
            try:
                migrate_credentials(migration_engine)
            finally:
                migration_engine.dispose()
        except BaseException:
            if previous:
                restore(previous)
                print('Migration failed; previous database restored.', file=sys.stderr)
            raise
    print('Database ready')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'serve', 'backup', 'restore', 'import'])
    parser.add_argument('--source', type=Path)
    args = parser.parse_args()
    if args.source:
        args.source = args.source.resolve(strict=True)
    os.chdir(ROOT / 'backend')
    os.environ['DATABASE_URL'] = 'sqlite:///' + DATABASE.as_posix()
    if args.operation == 'prepare':
        prepare()
    elif args.operation == 'backup':
        print('Backup:', backup())
    elif args.operation in ('restore', 'import'):
        if not args.source:
            parser.error('restore requires --source <backup path>')
        with exclusive():
            if args.operation == 'import' and DATABASE.exists():
                raise RuntimeError('Database already exists; refusing to overwrite it')
            if args.operation == 'import':
                pending = DATABASE.with_name(DATABASE.name + '.importing')
                pending.unlink(missing_ok=True)
                try:
                    restore(args.source, pending)
                    pending.replace(DATABASE)
                finally:
                    pending.unlink(missing_ok=True)
                print('Database imported')
            else:
                print('Pre-restore backup:', restore(args.source))
        print('Database restored. Run prepare before starting.')
    else:
        import uvicorn
        from app.main import create_app
        with exclusive():
            validate(DATABASE)
            from app.core.credentials import cipher, decrypt_config
            from app.models import User
            from sqlalchemy.orm import Session
            from app.core.database import make_engine
            cipher()
            credential_engine = make_engine()
            try:
                with Session(credential_engine) as db:
                    for user in db.query(User):
                        decrypt_config(user.ai_config)
            finally:
                credential_engine.dispose()
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            if validate(DATABASE) != ScriptDirectory.from_config(Config('alembic.ini')).get_current_head():
                raise RuntimeError('Database migration required; run prepare')
            # Local HTTP defaults; production supplies HTTPS settings.
            os.environ.setdefault('COOKIE_SECURE', 'false')
            os.environ.setdefault('APP_ORIGIN', 'http://127.0.0.1:8765')
            os.environ['FRONTEND_DIST'] = str(ROOT / 'frontend/dist')
            # Avoid request URLs and request/model bodies in local logs.
            print('FNote: http://127.0.0.1:8765', flush=True)
            uvicorn.run(create_app(), host='127.0.0.1', port=8765, workers=1,
                access_log=False, log_level='warning', timeout_keep_alive=15,
                limit_concurrency=64, timeout_graceful_shutdown=10)


if __name__ == '__main__':
    main()
