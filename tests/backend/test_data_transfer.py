import json
import sqlite3

import pytest

from scripts.data_transfer import export_data, import_data


def snapshot(tmp_path, database_template):
    database = tmp_path / 'target.db'
    with sqlite3.connect(database_template) as src, sqlite3.connect(database) as dst:
        src.backup(dst)
    output = tmp_path / 'snapshot.json'
    export_data(database, output)
    return database, output


def test_round_trip(tmp_path, database_template):
    database, output = snapshot(tmp_path, database_template)
    with sqlite3.connect(database) as db:
        db.execute("UPDATE users SET username='修改后的账户' WHERE username='alice'")
    previous = import_data(database, output, replace=True, backup_directory=tmp_path / 'backups')
    assert previous.is_file()
    with sqlite3.connect(previous) as db:
        assert db.execute("SELECT 1 FROM users WHERE username='修改后的账户'").fetchone()
    second = tmp_path / 'second.json'
    export_data(database, second)
    assert json.loads(output.read_text('utf-8'))['tables'] == json.loads(second.read_text('utf-8'))['tables']
    with pytest.raises(ValueError, match='already exists'):
        export_data(database, output)


def test_refuse_occupied_target(tmp_path, database_template):
    database, output = snapshot(tmp_path, database_template)
    with pytest.raises(ValueError, match='contains data'):
        import_data(database, output)


@pytest.mark.parametrize('damage', ['foreign_key', 'unique', 'schema', 'missing_table'])
def test_invalid_import_preserves_database(tmp_path, database_template, damage):
    database, output = snapshot(tmp_path, database_template)
    payload = json.loads(output.read_text('utf-8'))
    if damage == 'foreign_key':
        payload['tables']['users']['rows'] = []
        # Create an orphan even when the seeded template has no dependent records.
        entry = payload['tables']['exercise_preferences']
        entry['rows'] = [['missing-user', 'missing-exercise', 1, 1]]
    elif damage == 'unique':
        payload['tables']['users']['rows'].append(payload['tables']['users']['rows'][0])
    elif damage == 'schema':
        payload['schema'] = []
    else:
        del payload['tables']['messages']
    output.write_text(json.dumps(payload), encoding='utf-8')
    with pytest.raises((ValueError, sqlite3.Error)):
        import_data(database, output, replace=True, backup_directory=tmp_path / 'backups')
    after = tmp_path / 'after.json'
    export_data(database, after)
    with sqlite3.connect(database_template) as db:
        assert json.loads(after.read_text('utf-8'))['tables']['users']['rows'] == [list(r) for r in db.execute('SELECT * FROM users')]
