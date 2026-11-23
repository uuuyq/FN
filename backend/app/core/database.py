import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


def make_engine(url=None):
    if sqlite3.sqlite_version_info < (3, 51, 3):
        raise RuntimeError('SQLite >= 3.51.3 is required for WAL safety')
    url = url or os.getenv('DATABASE_URL', 'sqlite:///./data/fnote.db')
    if not url.startswith('sqlite:///') or ':memory:' in url:
        raise RuntimeError('Use a local SQLite file database')
    Path(url.removeprefix('sqlite:///')).resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 5})

    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA busy_timeout=5000')
        connection.execute('PRAGMA journal_mode=WAL')

    return engine


@contextmanager
def write_transaction(engine):
    # SQLite serializes all read/validate/write operations; no model calls inside.
    with Session(engine, expire_on_commit=False) as session:
        try:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
