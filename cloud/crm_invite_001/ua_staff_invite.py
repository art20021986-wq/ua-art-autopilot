"""Is this text a valid one-time staff invite from the CRM bot («👥 Сотрудники» → «➕ Добавить …»)? (ORDER-PROCESS-001)

The access guard (bezopasnost.py) asks this before refusing an unknown person, so the invite reaches the CRM bot,
which consumes it and gives the role. Read-only: the code must exist in crm.db, be unused and be at most 24 hours old.
"""
import datetime
import re
import sqlite3
from contextlib import closing

CODE = re.compile(r'[0-9A-F]{6}')
MAX_AGE = datetime.timedelta(hours=24)


def valid(text, db_path, now=None):
    code = (text or '').strip().upper()
    if not CODE.fullmatch(code):
        return False
    with closing(sqlite3.connect('file:%s?mode=ro' % db_path, uri=True, timeout=5)) as connection:
        row = connection.execute('SELECT created_at FROM invites WHERE code=? AND used_by IS NULL', (code,)).fetchone()
    if row is None:
        return False
    try:
        created = datetime.datetime.fromisoformat(row[0])
    except (TypeError, ValueError):
        return False
    # db.now() writes local server time without a zone; compare on the same clock.
    return (now or datetime.datetime.now()) - created <= MAX_AGE
