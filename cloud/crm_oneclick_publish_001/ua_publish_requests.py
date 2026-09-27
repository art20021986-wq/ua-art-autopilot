"""Durable explicit publication requests; no HTML rendering or CRM row writes."""
from contextlib import contextmanager
from pathlib import Path
import os
import sqlite3
import time
import uuid


@contextmanager
def connection(root):
    directory = Path(root) / '.crm_publish_requests'
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    conn = sqlite3.connect(directory / 'requests.sqlite3', timeout=2)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('''CREATE TABLE IF NOT EXISTS requests (
            identity TEXT PRIMARY KEY, code TEXT NOT NULL, token TEXT NOT NULL,
            revision TEXT NOT NULL, state TEXT NOT NULL, verified_revision TEXT,
            chat_id INTEGER NOT NULL, message_id INTEGER NOT NULL,
            delivered INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)''')
        with conn:
            yield conn
    finally:
        conn.close()


def enqueue(root, identity, revision, chat_id, message_id):
    identity = str(int(identity))
    with connection(root) as conn:
        conn.execute('BEGIN IMMEDIATE')
        old = conn.execute('SELECT * FROM requests WHERE identity=?', (identity,)).fetchone()
        if old and old['state'] == 'pending' and old['revision'] == revision['sha256']:
            # A second tap joins the current request; it does not reset retries.
            conn.execute('UPDATE requests SET chat_id=?, message_id=? WHERE identity=?',
                         (chat_id, message_id, identity))
            return old['token']
        token = uuid.uuid4().hex
        conn.execute('''INSERT OR REPLACE INTO requests
            (identity,code,token,revision,state,verified_revision,chat_id,message_id,delivered,created)
            VALUES (?,?,?,?,'pending',NULL,?,?,0,?)''',
            (identity, revision['code'], token, revision['sha256'], chat_id, message_id, time.time()))
        return token


def pending(root):
    with connection(root) as conn:
        return {row['identity']: dict(row) for row in conn.execute(
            "SELECT * FROM requests WHERE state='pending' ORDER BY created")}


def finish(root, token, state, revision=None):
    if state not in ('verified', 'cancelled'):
        raise ValueError('INVALID_REQUEST_STATE')
    with connection(root) as conn:
        # A superseded request cannot complete the newer one.
        return conn.execute('''UPDATE requests SET state=?, verified_revision=?
            WHERE token=? AND state='pending' ''', (state, revision, token)).rowcount == 1


def receipts(root):
    with connection(root) as conn:
        return [dict(row) for row in conn.execute(
            "SELECT * FROM requests WHERE state!='pending' AND delivered=0 ORDER BY created LIMIT 20")]


def current(root, token):
    with connection(root) as conn:
        row = conn.execute('SELECT * FROM requests WHERE token=?', (token,)).fetchone()
        return dict(row) if row else None


def delivered(root, token):
    with connection(root) as conn:
        conn.execute("UPDATE requests SET delivered=1 WHERE token=? AND state!='pending'", (token,))
