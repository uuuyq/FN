"""Log failure locations without exception messages, SQL or user values."""
import logging
import re
import traceback
from pathlib import Path


def report_failure(stage, error):
    # Flush may fail first, then rollback may fail and mask that exception.
    # Walk both links: a DBAPI wrapper's explicit cause can hide its context.
    pending = [('raised', error)]
    seen = set()
    while pending and len(seen) < 32:
        relation, current = pending.pop(0)
        if not isinstance(current, BaseException) or id(current) in seen:
            continue
        seen.add(id(current))
        frames = traceback.extract_tb(current.__traceback__)
        locations = ' > '.join(f'{Path(frame.filename).name}:{frame.lineno}:{frame.name}' for frame in frames)
        original = getattr(current, 'orig', current)
        sqlite_name = getattr(original, 'sqlite_errorname', '')
        if not isinstance(sqlite_name, str) or not re.fullmatch(r'SQLITE_[A-Z_]+', sqlite_name):
            sqlite_name = '-'
        logging.getLogger('uvicorn.error').error(
            'failure stage=%s exception=%s sqlite=%s relation=%s frames=%s',
            stage, type(current).__name__, sqlite_name, relation, locations,
        )
        pending.extend((link, linked) for link, linked in (
            ('cause', current.__cause__), ('context', current.__context__),
            ('driver', getattr(current, 'orig', None))) if linked is not None)
