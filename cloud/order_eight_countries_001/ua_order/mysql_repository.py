"""Native MySQL transactions using the host's existing mysqlclient driver."""
import hashlib
import json
from pathlib import Path
import secrets
import time

from .contract import Conflict, encoded
from .mysql_schema import DDL, TABLES
from .storage import NotFound, StorageUnavailable, detail, receipt


class MySQLRepository:
    def __init__(self, *, host, user, database, defaults_file, clock=time.time):
        if database not in (user + '$orders', user + '$orders_test'):
            raise ValueError('An isolated orders database is required')
        self.options = dict(host=host, user=user, database=database,
                            read_default_file=str(Path(defaults_file).expanduser().resolve()))
        self.clock = clock

    def _run(self, operation, *, write=False):
        # Each call owns its connection. No idle shared connection or connection
        # sharing across WSGI threads / bot processes.
        import MySQLdb
        from MySQLdb.cursors import DictCursor
        for attempt in range(3):
            db = None
            try:
                db = MySQLdb.connect(**self.options, charset='utf8mb4',
                                     cursorclass=DictCursor, connect_timeout=3,
                                     read_timeout=5, write_timeout=5,
                                     autocommit=False)
                with db.cursor() as cursor:
                    cursor.execute('SET SESSION innodb_lock_wait_timeout=3')
                    cursor.execute("SET SESSION sql_mode='STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'")
                    result = operation(cursor)
                if write:
                    db.commit()
                else:
                    db.rollback()
                return result  # Never acknowledge before commit.
            except BaseException as error:
                if db is not None:
                    try:
                        db.rollback()
                    except MySQLdb.Error:
                        pass
                if isinstance(error, MySQLdb.Error):
                    # Replay only known transaction-abort cases. A lost commit
                    # response is resolved by the request UUID on client retry.
                    if error.args and error.args[0] in (1205, 1213) and attempt < 2:
                        time.sleep(0.025 * (attempt + 1))
                        continue
                    raise StorageUnavailable('Order storage unavailable') from None
                raise
            finally:
                if db is not None:
                    db.close()

    @staticmethod
    def _tables(cursor):
        cursor.execute('SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()')
        return {r['TABLE_NAME']: r['ENGINE'] for r in cursor.fetchall()}

    def _check(self, cursor):
        tables = self._tables(cursor)
        if set(tables) != TABLES or any(v != 'InnoDB' for v in tables.values()):
            raise ValueError('The isolated order schema is incomplete or unrelated')
        cursor.execute('SELECT name, version FROM order_schema')
        if list(cursor.fetchall()) != [{'name': 'ua_orders', 'version': 1}]:
            raise ValueError('Unsupported order database version')

    def check_ready(self):
        self._run(self._check)

    def initialize(self):
        # DDL is not transactional in MySQL. An interrupted initialization is
        # rejected, never silently repaired or applied to an unrelated schema.
        def initialize(cursor):
            if self._tables(cursor):
                self._check(cursor)
                return
            for statement in DDL:
                cursor.execute(statement)
            cursor.execute("INSERT INTO order_schema VALUES ('ua_orders', 1)")
        self._run(initialize, write=True)
        self.check_ready()

    def save(self, data, payload_hash, owner, channel, event=None):
        def save(cursor):
            request_id, now = data['request_id'], int(self.clock())
            cursor.execute('''INSERT INTO order_requests
                (request_id,owner,payload_hash,payload,channel,created_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE request_id=request_id''',
                           (request_id, owner, payload_hash, encoded(data), channel, now))
            cursor.execute('SELECT * FROM order_requests WHERE request_id=%s FOR UPDATE', (request_id,))
            row = cursor.fetchone()
            if row['owner'] != owner or row['payload_hash'] != payload_hash:
                raise Conflict('request_conflict')
            if event:
                cursor.execute('''INSERT INTO order_events VALUES (%s,%s)
                    ON DUPLICATE KEY UPDATE event=event''', (event, request_id))
                cursor.execute('SELECT request_id FROM order_events WHERE event=%s FOR UPDATE', (event,))
                if cursor.fetchone()['request_id'] != request_id:
                    raise Conflict('event_conflict')
            cursor.execute('''INSERT INTO order_outbox (request_id,available_at) VALUES (%s,%s)
                ON DUPLICATE KEY UPDATE request_id=request_id''', (request_id, now))
            return receipt(row)
        return self._run(save, write=True)

    def _one(self, sql, values, transform):
        def fetch(cursor):
            cursor.execute(sql, values)
            row = cursor.fetchone()
            if not row:
                raise NotFound()
            return transform(row)
        return self._run(fetch)

    def receipt_for_owner(self, request_id, owner):
        return self._one('SELECT * FROM order_requests WHERE request_id=%s AND owner=%s',
                         (request_id, owner), receipt)

    def detail(self, row_id):
        return self._one('SELECT * FROM order_requests WHERE id=%s', (row_id,), detail)

    def notification_data(self, request_id):
        return self._one('SELECT * FROM order_requests WHERE request_id=%s', (request_id,), detail)

    def list_requests(self, *, before=None, limit=20):
        if not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError('Invalid page size')
        def fetch(cursor):
            cursor.execute('SELECT * FROM order_requests WHERE id < %s ORDER BY id DESC LIMIT %s',
                           (before if before is not None else 9223372036854775807, limit + 1))
            rows = cursor.fetchall()
            visible = rows[:limit]
            return [detail(r) for r in visible], visible[-1]['id'] if len(rows) > limit else None
        return self._run(fetch)

    def notification_recipients_sent(self, request_id):
        def fetch(cursor):
            cursor.execute('SELECT recipient FROM order_notification_receipts WHERE request_id=%s', (request_id,))
            return {row['recipient'] for row in cursor.fetchall()}
        return self._run(fetch)

    def notification_recipient_sent(self, request_id, recipient):
        self._run(lambda cursor: cursor.execute('''INSERT INTO order_notification_receipts VALUES (%s,%s,%s)
            ON DUPLICATE KEY UPDATE sent_at=sent_at''',
            (request_id, recipient, int(self.clock()))), write=True)

    def create_draft(self, data, owner):
        token = secrets.token_urlsafe(24)
        hashed, now = hashlib.sha256(token.encode()).hexdigest(), int(self.clock())
        def create(cursor):
            cursor.execute('DELETE FROM order_drafts WHERE expires_at < %s', (now,))
            cursor.execute('INSERT INTO order_drafts VALUES (%s,%s,%s,%s,NULL)',
                           (hashed, owner, encoded(data), now + 1800))
        self._run(create, write=True)
        return token

    def redeem_draft(self, token, telegram_owner):
        if not telegram_owner.startswith('telegram:') or len(token) != 32:
            raise NotFound()
        hashed = hashlib.sha256(token.encode()).hexdigest()
        def redeem(cursor):
            cursor.execute('SELECT * FROM order_drafts WHERE token_hash=%s AND expires_at>%s FOR UPDATE',
                           (hashed, int(self.clock())))
            row = cursor.fetchone()
            if not row or row['telegram_owner'] not in (None, telegram_owner):
                raise NotFound()
            cursor.execute('UPDATE order_drafts SET telegram_owner=%s WHERE token_hash=%s', (telegram_owner, hashed))
            return json.loads(row['payload'])
        return self._run(redeem, write=True)

    def claim_notification(self):
        now = int(self.clock())
        def claim(cursor):
            cursor.execute('''SELECT * FROM order_outbox WHERE
                (state='pending' AND available_at<=%s) OR (state='sending' AND lease_until<=%s)
                ORDER BY id LIMIT 1 FOR UPDATE''', (now, now))
            row = cursor.fetchone()
            if not row:
                return None
            lease = secrets.token_hex(16)
            cursor.execute("UPDATE order_outbox SET state='sending',lease=%s,lease_until=%s,attempts=attempts+1 WHERE id=%s",
                           (lease, now + 60, row['id']))
            return dict(id=row['id'], request_id=row['request_id'], lease=lease)
        return self._run(claim, write=True)

    def finish_notification(self, claim, *, delivered):
        def finish(cursor):
            cursor.execute('SELECT attempts FROM order_outbox WHERE id=%s AND lease=%s FOR UPDATE',
                           (claim['id'], claim['lease']))
            row = cursor.fetchone()
            if not row:
                return
            if delivered:
                cursor.execute("UPDATE order_outbox SET state='sent',lease=NULL,lease_until=NULL WHERE id=%s AND lease=%s",
                               (claim['id'], claim['lease']))
            else:
                delay = min(3600, 60 * 2 ** min(6, row['attempts'] - 1))
                cursor.execute("UPDATE order_outbox SET state='pending',available_at=%s,lease=NULL,lease_until=NULL WHERE id=%s AND lease=%s",
                               (int(self.clock()) + delay, claim['id'], claim['lease']))
        self._run(finish, write=True)
