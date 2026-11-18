import os
from alembic import context
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
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
            # Upgrade databases created before the migration history was consolidated.
            inspector = inspect(connection)
            if inspector.has_table('alembic_version'):
                revision = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
                if revision in ('0001', '0002', '0003', '0004', '0005') and inspector.has_table('equipment'):
                    has_category = any(column['name'] == 'category' for column in inspector.get_columns('equipment'))
                    user_has_category = any(column['name'] == 'category' for column in inspector.get_columns('user_exercises'))
                    initial = ScriptDirectory.from_config(config).get_revision('0001').module
                    with Operations.context(MigrationContext.configure(connection)):
                        if not inspector.has_table('agent_operations'):
                            initial.upgrade_operations()
                        if revision in ('0001', '0002') and not has_category:
                            initial.upgrade_profile()
                        if not has_category:
                            initial.upgrade_categories()
                        if not user_has_category:
                            initial.upgrade_user_category()
                        initial.upgrade_training_parts()
                    connection.execute(text("UPDATE alembic_version SET version_num = '0001'"))
            with context.begin_transaction():
                context.run_migrations()
            if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('Migration left invalid foreign key references')
    finally:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.commit()
engine.dispose()
