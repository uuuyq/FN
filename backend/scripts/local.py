"""Single-process Windows loopback deployment and verified SQLite backups."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'runtime'
DATABASE = ROOT / 'backend/data/fitplan.db'


def validate(path):
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('Database integrity validation failed')
        db.execute('SELECT id FROM users LIMIT 1')
        return db.execute('SELECT version_num FROM alembic_version').fetchone()[0]


def backup(source=None, directory=None):
    source = Path(source or DATABASE).resolve(strict=True)
    directory = Path(directory or RUNTIME / 'backups').resolve()
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8] + '.db')
    try:
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
        validate(destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


@contextmanager
def exclusive(directory=None):
    """OS releases the lock on normal exit or crash; stale PID files don't lock."""
    import msvcrt
    directory = Path(directory or RUNTIME)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'instance.lock').open('a+b') as handle:
        try:
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b'0'); handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError('FitPlan is running; stop it before migration or restore') from None
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def restore(source, destination=None, backup_directory=None):
    source, destination = Path(source).resolve(strict=True), Path(destination or DATABASE).resolve()
    validate(source)
    if source == destination:
        raise RuntimeError('Source and destination must differ')
    # Caller must hold exclusive lock and stop all writers. Preserve current DB.
    previous = backup(destination, backup_directory) if destination.exists() else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(destination) as dst:
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
        except BaseException:
            if previous:
                restore(previous)
                print('Migration failed; previous database restored.', file=sys.stderr)
            raise
    print('Database ready')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['prepare', 'serve', 'backup', 'restore'])
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
    elif args.operation == 'restore':
        if not args.source:
            parser.error('restore requires --source <backup path>')
        with exclusive():
            print('Pre-restore backup:', restore(args.source))
        print('Database restored. Run prepare before starting.')
    else:
        import uvicorn
        from app.main import create_app
        with exclusive():
            validate(DATABASE)
            from alembic.config import Config
            from alembic.script import ScriptDirectory
            if validate(DATABASE) != ScriptDirectory.from_config(Config('alembic.ini')).get_current_head():
                raise RuntimeError('Database migration required; run prepare')
            os.environ['COOKIE_SECURE'] = 'false'  # Loopback HTTP only.
            os.environ['APP_ORIGIN'] = 'http://127.0.0.1:8765'
            os.environ['FRONTEND_DIST'] = str(ROOT / 'frontend/dist')
            # Avoid request URLs and request/model bodies in local logs.
            print('FitPlan: http://127.0.0.1:8765', flush=True)
            uvicorn.run(create_app(), host='127.0.0.1', port=8765, workers=1,
                access_log=False, log_level='warning', timeout_keep_alive=15,
                limit_concurrency=64, timeout_graceful_shutdown=10)


if __name__ == '__main__':
    main()
