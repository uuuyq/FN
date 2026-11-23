"""Deployment data safety checks; never touch the real application database."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest
from scripts import local


def database(path):
    with sqlite3.connect(path) as db:
        db.executescript("CREATE TABLE users(id INTEGER PRIMARY KEY); INSERT INTO users VALUES(42);"
                         "CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('test');")
    return path


def test_backup_unique_and_restorable(tmp_path):
    source = database(tmp_path / 'source.db')
    directory = tmp_path / 'backups'
    first = local.backup(source, directory)
    second = local.backup(source, directory)
    assert first != second
    destination = tmp_path / 'restored.db'
    local.restore(first, destination)
    assert local.validate(destination) == 'test'
    with sqlite3.connect(destination) as db:
        assert db.execute('SELECT id FROM users').fetchone() == (42,)
    assert not list(directory.glob('*.partial'))


def test_backup_retention_only_owned_files_after_success(tmp_path):
    source = database(tmp_path / 'source.db')
    directory = tmp_path / 'backups'
    directory.mkdir()
    now = datetime.now(timezone.utc)
    def entry(days):
        stamp = (now - timedelta(days=days)).strftime('%Y%m%dT%H%M%SZ')
        file = directory / f'fnote-{stamp}-{"a" * 32}.db'
        file.write_bytes(b'old')
        return file
    expired, recent = entry(31), entry(29)
    unrelated = directory / 'manual-backup.db'
    unrelated.write_bytes(b'manual')
    local.backup(source, directory)
    assert not expired.exists()
    assert recent.exists() and unrelated.exists()


def test_failed_backup_keeps_history(tmp_path, monkeypatch):
    source = database(tmp_path / 'source.db')
    directory = tmp_path / 'backups'
    directory.mkdir()
    old = directory / f'fnote-20000101T000000Z-{"a" * 32}.db'
    old.write_bytes(b'history')
    def fail(_):
        raise RuntimeError('invalid')
    monkeypatch.setattr(local, 'validate', fail)
    with pytest.raises(RuntimeError, match='invalid'):
        local.backup(source, directory)
    assert list(directory.iterdir()) == [old]


def test_backup_includes_committed_wal(tmp_path):
    source = database(tmp_path / 'source.db')
    with sqlite3.connect(source) as writer:
        writer.execute('PRAGMA journal_mode=WAL')
        writer.execute('INSERT INTO users VALUES(43)')
        writer.commit()
        result = local.backup(source, tmp_path / 'backups')
        with sqlite3.connect(result) as reader:
            assert reader.execute('SELECT count(*) FROM users').fetchone()[0] == 2


def test_lock_excludes_other_process_and_releases(tmp_path):
    code = 'from scripts.local import exclusive; from pathlib import Path; import sys\nwith exclusive(Path(sys.argv[1])): pass'
    with local.exclusive(tmp_path):
        result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True)
        assert result.returncode != 0
        assert 'FNote is running' in result.stderr
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_import_respects_configured_path_and_refuses_overwrite(tmp_path):
    source = database(tmp_path / 'upload.db')
    target = tmp_path / 'data' / 'fnote.db'
    env = dict(os.environ, FNOTE_DATABASE=str(target), FNOTE_RUNTIME=str(tmp_path / 'run'),
               FNOTE_BACKUPS=str(tmp_path / 'backups'))
    command = [sys.executable, '-m', 'scripts.local', 'import', '--source', str(source)]
    first = subprocess.run(command, env=env, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert local.validate(target) == 'test'
    second = subprocess.run(command, env=env, capture_output=True, text=True)
    assert second.returncode != 0
    assert 'refusing to overwrite' in second.stderr
    assert local.validate(target) == 'test'


def test_prepare_uses_external_database_and_keeps_upgrade_backup(tmp_path, database_template):
    target = tmp_path / 'data' / 'fnote.db'
    env = dict(os.environ, FNOTE_DATABASE=str(target), FNOTE_RUNTIME=str(tmp_path / 'run'),
               FNOTE_BACKUPS=str(tmp_path / 'backups'))
    imported = subprocess.run([sys.executable, '-m', 'scripts.local', 'import', '--source', str(database_template)],
                              env=env, capture_output=True, text=True)
    assert imported.returncode == 0, imported.stderr
    prepared = subprocess.run([sys.executable, '-m', 'scripts.local', 'prepare'],
                              env=env, capture_output=True, text=True)
    assert prepared.returncode == 0, prepared.stderr
    backups = list((tmp_path / 'backups').glob('fnote-*.db'))
    assert len(backups) == 1
    assert local.validate(target) == local.validate(backups[0])
