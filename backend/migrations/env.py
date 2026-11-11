import os
from alembic import context
from app.core.database import Base, make_engine
from app import models

config = context.config
engine = make_engine(os.getenv('DATABASE_URL', config.get_main_option('sqlalchemy.url')))
with engine.connect() as connection:
    # SQLite batch table replacement needs FK enforcement disabled on this
    # connection. Check all references before committing the atomic migration.
    connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
    connection.commit()
    try:
        with connection.begin():
            connection.exec_driver_sql('BEGIN IMMEDIATE')
            context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True)
            with context.begin_transaction():
                context.run_migrations()
            if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Migration left invalid foreign key references')
    finally:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.commit()
engine.dispose()
