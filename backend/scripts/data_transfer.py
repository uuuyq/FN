"""Export/import a complete FNote data snapshot (JSON, no schema execution)."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone

from scripts.local import DATABASE, backup, exclusive


def quote(name):
    return '"' + name.replace('"', '""') + '"'


@contextmanager
def connect(path, readonly=False):
    path = Path(path).resolve(strict=True)
    db = sqlite3.connect(path.as_uri() + ('?mode=ro' if readonly else '?mode=rw'),
                         uri=True, timeout=5)
    try:
        with db:
            yield db
    finally:
        db.close()


def schema(db):
    return [list(row) for row in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name")]


def tables(db):
    return [row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def check(db):
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
        raise ValueError('Database integrity check failed')
    if db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Database foreign key check failed')


def export_data(database, output):
    database = Path(database).resolve(strict=True)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Output already exists; choose a new output path')
    with connect(database, readonly=True) as db:
        db.execute('BEGIN')  # Schema and all rows belong to one read snapshot, including WAL.
        check(db)
        payload = {'format': 'fnote-data', 'version': 1,
                   'exported_at': datetime.now(timezone.utc).isoformat(),
                   'schema': schema(db), 'tables': {}}
        for name in tables(db):
            cursor = db.execute('SELECT * FROM ' + quote(name))
            payload['tables'][name] = {'columns': [c[0] for c in cursor.description],
                                       'rows': [list(row) for row in cursor]}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a complete JSON file; exclusive creation never overwrites a backup.
    fd, temporary = tempfile.mkstemp(dir=output.parent, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
        os.link(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {name: len(data['rows']) for name, data in payload['tables'].items()}


def import_data(database, source, replace=False, backup_directory=None):
    database = Path(database).resolve(strict=True)
    source = Path(source).resolve(strict=True)
    if database == source:
        raise ValueError('Source and database must differ')
    payload = json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(payload, dict) or payload.get('format') != 'fnote-data' or payload.get('version') != 1:
        raise ValueError('Unsupported data file format/version')
    previous = None
    with connect(database) as db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        check(db)
        names = tables(db)
        if payload.get('schema') != schema(db):
            raise ValueError('Schema mismatch; initialize the target with matching migrations first')
        data = payload.get('tables')
        if not isinstance(data, dict) or set(data) != set(names):
            raise ValueError('Snapshot must contain exactly all database tables')
        for name in names:
            columns = [row[1] for row in db.execute('PRAGMA table_info(' + quote(name) + ')')]
            entry = data[name]
            if (not isinstance(entry, dict) or entry.get('columns') != columns
                    or not isinstance(entry.get('rows'), list)
                    or any(not isinstance(row, list) or len(row) != len(columns)
                           or any(type(v) not in (str, int, float, type(None)) for v in row)
                           for row in entry['rows'])):
                raise ValueError('Invalid columns or rows for table ' + name)
        current_version = db.execute('SELECT version_num FROM alembic_version').fetchall()
        if data['alembic_version']['rows'] != [list(row) for row in current_version]:
            raise ValueError('Migration version mismatch')
        occupied = any(db.execute('SELECT 1 FROM ' + quote(name) + ' LIMIT 1').fetchone()
                       for name in names if name != 'alembic_version')
        if occupied and not replace:
            raise ValueError('Target contains data; use --replace to replace all data')
        if replace:
            # Separate read connection can back up while this connection holds the writer lock.
            previous = backup(database, backup_directory)
        db.execute('PRAGMA defer_foreign_keys=ON')
        for name in names:
            db.execute('DELETE FROM ' + quote(name))
        for name in names:
            entry = data[name]
            sql = ('INSERT INTO ' + quote(name) + ' ('
                   + ','.join(map(quote, entry['columns'])) + ') VALUES ('
                   + ','.join('?' for _ in entry['columns']) + ')')
            db.executemany(sql, entry['rows'])
        check(db)  # Any failure rolls the entire replacement back.
    return previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DATABASE)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export')
    export.add_argument('--output', type=Path, required=True)
    restore = sub.add_parser('import')
    restore.add_argument('--input', type=Path, required=True)
    restore.add_argument('--replace', action='store_true')
    try:
        args = parser.parse_args()
        if args.command == 'export':
            print(json.dumps(export_data(args.database, args.output), ensure_ascii=False))
            print('Exported:', args.output.resolve())
        else:
            with exclusive():
                previous = import_data(args.database, args.input, args.replace)
            if previous:
                print('Pre-import backup:', previous)
            print('Import complete')
        return 0
    except (OSError, ValueError, sqlite3.Error, RuntimeError) as error:
        print('Data transfer failed:', error, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
