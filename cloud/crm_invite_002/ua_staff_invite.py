"""Is this text a valid one-time staff invite from the CRM bot («👥 Сотрудники» → «➕ Добавить …»)? (ORDER-PROCESS-001)

The access guard (bezopasnost.py) asks this before refusing an unknown person, so the invite reaches the CRM bot,
which consumes it and gives the role. Read-only: the code must exist in crm.db and be unused. No time limit
(owner 2026-11-05): a code works until it is used once.
"""
import re
import sqlite3
from contextlib import closing

CODE = re.compile(r'[0-9A-F]{6}')


def valid(text, db_path):
    code = (text or '').strip().upper()
    if not CODE.fullmatch(code):
        return False
    with closing(sqlite3.connect('file:%s?mode=ro' % db_path, uri=True, timeout=5)) as connection:
        row = connection.execute('SELECT 1 FROM invites WHERE code=? AND used_by IS NULL', (code,)).fetchone()
    return row is not None
