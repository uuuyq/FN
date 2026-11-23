"""Run from backend: python -m scripts.cleanup_workouts (safe to schedule daily)."""
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.database import make_engine, write_transaction
from app.modules.workouts.service import purge_expired_workouts


def main():
    root = Path(__file__).resolve().parents[2]
    runtime = Path(os.getenv('FNOTE_RUNTIME', str(root / 'runtime')))
    runtime.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[RotatingFileHandler(runtime / 'workout-cleanup.log',
                                  maxBytes=1048576, backupCount=3, encoding='utf-8'),
                                  logging.StreamHandler()])
    engine = None
    try:
        # Use the application's database explicitly; never create an empty database
        # because Task Scheduler launched from an unexpected working directory.
        database = Path(os.getenv('FNOTE_DATABASE', str(root / 'backend/data/fnote.db'))).resolve(strict=True)
        engine = make_engine('sqlite:///' + database.as_posix())
        with write_transaction(engine) as db:
            count = purge_expired_workouts(db)
        logging.info('Purged %s expired workouts', count)
        return 0
    except Exception:
        logging.exception('Workout cleanup failed')
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
