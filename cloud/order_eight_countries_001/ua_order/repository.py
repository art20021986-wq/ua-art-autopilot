"""Short SQLite transactions. This database contains enquiries, never inventory."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time

from .contract import Conflict, encoded
from .storage import NotFound, detail, receipt

APPLICATION_ID = 0x55414F52
DDL = '''
CREATE TABLE IF NOT EXISTS order_requests (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 request_id TEXT NOT NULL UNIQUE, owner TEXT NOT NULL,
 payload_hash TEXT NOT NULL, payload TEXT NOT NULL,
 channel TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS order_events (
 event TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES order_requests(request_id));
CREATE TABLE IF NOT EXISTS order_outbox (
 id INTEGER PRIMARY KEY, request_id TEXT NOT NULL UNIQUE REFERENCES order_requests(request_id),
 state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 available_at INTEGER NOT NULL, lease TEXT, lease_until INTEGER);
CREATE INDEX IF NOT EXISTS order_outbox_due ON order_outbox(state,available_at);
CREATE TABLE IF NOT EXISTS order_drafts (
 token_hash TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL,
 expires_at INTEGER NOT NULL, telegram_owner TEXT);
CREATE TABLE IF NOT EXISTS order_notification_receipts (
 request_id TEXT NOT NULL REFERENCES order_requests(request_id),
 recipient INTEGER NOT NULL, sent_at INTEGER NOT NULL,
 PRIMARY KEY (request_id, recipient));
'''


class Repository:
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path).resolve()
        self.clock = clock
        if self.path.name != 'order_requests.db':
            raise ValueError('An explicit isolated order_requests.db path is required')

    def initialize(self):
        # Explicit startup step, never import-time migration of the main CRM DB.
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            fd = None
        if fd is not None:
            os.close(fd)
        with self.connection() as db:
            app_id = db.execute('PRAGMA application_id').fetchone()[0]
            if db.execute('PRAGMA user_version').fetchone()[0] not in (0,1):
                raise ValueError('Unsupported order database version')
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            if app_id not in (0, APPLICATION_ID) or (app_id == 0 and tables):
                raise ValueError('Refusing an unrelated database')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute(f'PRAGMA application_id={APPLICATION_ID}')
            db.executescript(DDL)
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def connection(self, *, write=False):
        # Only initialize() may create the file; a bad runtime path must not
        # silently create an empty database alongside the real one.
        db = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True,
                             timeout=3, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    receipt = staticmethod(receipt)

    def save(self, data, payload_hash, owner, channel, event=None):
        with self.connection(write=True) as db:
            row = db.execute('SELECT * FROM order_requests WHERE request_id=?',
                             (data['request_id'],)).fetchone()
            replay = db.execute('SELECT request_id FROM order_events WHERE event=?', (event,)).fetchone() if event else None
            if replay and replay['request_id'] != data['request_id']:
                raise Conflict('event_conflict')
            if row:
                if row['owner'] != owner or row['payload_hash'] != payload_hash:
                    raise Conflict('request_conflict')
            else:
                db.execute('INSERT INTO order_requests(request_id,owner,payload_hash,payload,channel,created_at) VALUES (?,?,?,?,?,?)',
                           (data['request_id'], owner, payload_hash, encoded(data), channel, int(self.clock())))
                db.execute('INSERT INTO order_outbox(request_id,available_at) VALUES (?,?)',
                           (data['request_id'], int(self.clock())))
                row = db.execute('SELECT * FROM order_requests WHERE request_id=?', (data['request_id'],)).fetchone()
            if event and not replay:
                db.execute('INSERT INTO order_events VALUES (?,?)', (event, data['request_id']))
            result = self.receipt(row)
        return result  # Only after the transaction has committed.

    def receipt_for_owner(self, request_id, owner):
        with self.connection() as db:
            row = db.execute('SELECT * FROM order_requests WHERE request_id=? AND owner=?',
                             (request_id, owner)).fetchone()
            if not row:
                raise NotFound()
            return self.receipt(row)

    def list_requests(self, *, before=None, limit=20):
        if not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError('Invalid page size')
        with self.connection() as db:
            rows = db.execute('SELECT * FROM order_requests WHERE id < ? ORDER BY id DESC LIMIT ?',
                              (before if before is not None else 9223372036854775807, limit + 1)).fetchall()
            visible = rows[:limit]
            return [self._detail(r) for r in visible], visible[-1]['id'] if len(rows) > limit else None

    _detail = staticmethod(detail)

    def detail(self, row_id):
        with self.connection() as db:
            row = db.execute('SELECT * FROM order_requests WHERE id=?', (row_id,)).fetchone()
            if not row:
                raise NotFound()
            return self._detail(row)

    def notification_data(self, request_id):
        with self.connection() as db:
            row=db.execute('SELECT * FROM order_requests WHERE request_id=?',(request_id,)).fetchone()
            if not row: raise NotFound()
            return self._detail(row)

    def notification_recipients_sent(self, request_id):
        with self.connection() as db:
            return {row[0] for row in db.execute(
                'SELECT recipient FROM order_notification_receipts WHERE request_id=?', (request_id,))}

    def notification_recipient_sent(self, request_id, recipient):
        with self.connection(write=True) as db:
            db.execute('INSERT OR IGNORE INTO order_notification_receipts VALUES (?,?,?)',
                       (request_id, recipient, int(self.clock())))

    def create_draft(self, data, owner):
        token = secrets.token_urlsafe(24)
        hashed = hashlib.sha256(token.encode()).hexdigest()
        with self.connection(write=True) as db:
            db.execute('DELETE FROM order_drafts WHERE expires_at < ?', (int(self.clock()),))
            db.execute('INSERT INTO order_drafts VALUES (?,?,?,?,NULL)',
                       (hashed, owner, encoded(data), int(self.clock()) + 1800))
        return token

    def redeem_draft(self, token, telegram_owner):
        if not telegram_owner.startswith('telegram:') or len(token) != 32:
            raise NotFound()
        hashed = hashlib.sha256(token.encode()).hexdigest()
        with self.connection(write=True) as db:
            row = db.execute('SELECT * FROM order_drafts WHERE token_hash=? AND expires_at>?',
                             (hashed, int(self.clock()))).fetchone()
            if not row or row['telegram_owner'] not in (None, telegram_owner):
                raise NotFound()
            db.execute('UPDATE order_drafts SET telegram_owner=? WHERE token_hash=?', (telegram_owner, hashed))
            return json.loads(row['payload'])

    def claim_notification(self):
        now = int(self.clock())
        with self.connection(write=True) as db:
            row = db.execute("SELECT * FROM order_outbox WHERE (state='pending' AND available_at<=?) OR (state='sending' AND lease_until<=?) ORDER BY id LIMIT 1", (now, now)).fetchone()
            if not row:
                return None
            lease = secrets.token_hex(16)
            db.execute("UPDATE order_outbox SET state='sending',lease=?,lease_until=?,attempts=attempts+1 WHERE id=?", (lease, now + 60, row['id']))
            return dict(id=row['id'], request_id=row['request_id'], lease=lease)

    def finish_notification(self, claim, *, delivered):
        with self.connection(write=True) as db:
            if delivered:
                db.execute("UPDATE order_outbox SET state='sent',lease=NULL,lease_until=NULL WHERE id=? AND lease=?", (claim['id'], claim['lease']))
            else:
                row = db.execute('SELECT attempts FROM order_outbox WHERE id=? AND lease=?',
                                 (claim['id'], claim['lease'])).fetchone()
                if row:
                    delay = min(3600, 60 * 2 ** min(6, row['attempts'] - 1))
                    db.execute("UPDATE order_outbox SET state='pending',available_at=?,lease=NULL,lease_until=NULL WHERE id=? AND lease=?", (int(self.clock()) + delay, claim['id'], claim['lease']))
