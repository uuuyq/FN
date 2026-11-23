import json
import sqlite3
import pytest

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import error_detail, exception_detail
from app.agent.tools import workouts
from app.models import User, Workout
from helpers import call, content, reply, send, setup, write


def readonly_error():
    error = sqlite3.OperationalError('synthetic-sensitive-sql-or-key')
    error.sqlite_errorname = 'SQLITE_READONLY'
    return error


def test_error_categories_do_not_include_raw_details():
    error = exception_detail(readonly_error())
    assert error == error_detail('database_error')
    assert 'synthetic-sensitive' not in json.dumps(error)
    busy = sqlite3.OperationalError('private')
    busy.sqlite_errorname = 'SQLITE_BUSY'
    assert exception_detail(busy) == error_detail('database_busy')
    assert exception_detail(sqlite3.IntegrityError('private')) == error_detail('constraint_conflict')
    assert exception_detail(RuntimeError('private')) == error_detail('internal_error')


@pytest.mark.parametrize('flush_failure', [False, True])
def test_proposal_failure_reaches_agent_and_transaction_recovers(env, monkeypatch, flush_failure):
    _, (client, _) = env
    def fail(db, *args):
        if flush_failure:
            db.add(User(username='alice', password_hash='unused'))
            db.flush()  # A real constraint failure leaves the session needing rollback.
        raise readonly_error()
    monkeypatch.setattr(workouts, 'normalized_content', fail)
    calls = []
    def model(messages, tools):
        calls.append(True)
        if len(calls) == 1:
            return call('save', 'save_workout', content=content())
        result = json.loads(messages[-1]['content'])
        assert result['error'] == error_detail('constraint_conflict' if flush_failure else 'database_error')
        return reply('执行失败')
    cid, _ = setup(client, model)
    assert send(client, cid)['status'] == 'succeeded'
    assert len(calls) == 2


def test_confirmation_failure_rolls_back_written_workout(env, monkeypatch):
    engine, (client, _) = env
    original_save = workouts.save_workout
    def fail_after_write(*args):
        original_save(*args)
        raise readonly_error()
    monkeypatch.setattr(workouts, 'save_workout', fail_after_write)
    calls = []
    def model(messages, tools):
        calls.append(True)
        if len(calls) == 1:
            return call('save', 'save_workout', content=content())
        assert json.loads(messages[-1]['content'])['error'] == error_detail('database_error')
        return reply('执行失败')
    cid, _ = setup(client, model)
    card = send(client, cid)['result']
    result = write(client, '/conversation-actions/' + card['action_id'] + '/confirm', {'version': card['version']})
    assert result['status'] == 'failed'
    assert result['result']['error'] == error_detail('database_error')
    continuation = result['result']['continuation_turn_id']
    response = client.get('/api/turns/' + continuation + '/events')
    assert response.status_code == 200
    assert len(calls) == 2
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Workout)) == 0
