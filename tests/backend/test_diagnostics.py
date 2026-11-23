import logging
import sqlite3

from sqlalchemy.exc import OperationalError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest

from app.core.diagnostics import report_failure
from app.models import User


def test_failure_logs_locations_and_sqlite_code_without_values(caplog):
    sensitive = 'synthetic-private-api-key-and-training-data'
    with caplog.at_level(logging.ERROR, logger='uvicorn.error'):
        try:
            original = sqlite3.OperationalError(sensitive)
            original.sqlite_errorname = 'SQLITE_READONLY'
            raise OperationalError('INSERT ' + sensitive, {'key': sensitive}, original)
        except OperationalError as error:
            report_failure('action_confirmation', error)
    assert sensitive not in caplog.text
    assert 'INSERT' not in caplog.text
    assert 'SQLITE_READONLY' in caplog.text
    assert 'OperationalError' in caplog.text
    assert 'test_diagnostics.py:' in caplog.text


def test_failure_logs_original_flush_error_when_savepoint_rollback_masks_it(tmp_path, caplog):
    engine = create_engine('sqlite:///' + (tmp_path / 'rollback.db').as_posix())
    try:
        User.__table__.create(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql('''CREATE TRIGGER fail_user BEFORE INSERT ON users
                BEGIN SELECT RAISE(ROLLBACK, 'synthetic-private-trigger-value'); END''')
        with Session(engine) as db, caplog.at_level(logging.ERROR, logger='uvicorn.error'):
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            db.begin_nested()
            db.add(User(username='synthetic-private-username', password_hash='synthetic-private-hash'))
            with pytest.raises(OperationalError) as failure:
                db.flush()
            report_failure('action_confirmation', failure.value)
            db.rollback()
        # The outer failure is "no such savepoint"; the cause is the trigger rollback.
        assert 'sqlite=SQLITE_ERROR' in caplog.text
        assert 'sqlite=SQLITE_CONSTRAINT_TRIGGER' in caplog.text
        assert 'relation=context' in caplog.text
        assert 'synthetic-private' not in caplog.text
        assert 'INSERT' not in caplog.text
        assert 'RAISE' not in caplog.text
    finally:
        engine.dispose()


def test_failure_chain_handles_cycles(caplog):
    error = RuntimeError('private')
    error.__context__ = error
    with caplog.at_level(logging.ERROR, logger='uvicorn.error'):
        report_failure('cycle_test', error)
    assert len(caplog.records) == 1
