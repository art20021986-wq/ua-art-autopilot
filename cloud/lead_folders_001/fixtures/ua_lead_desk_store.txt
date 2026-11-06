"""Work state of site enquiries in the CRM database (ORDER-PROCESS-001): status, manager note, reminders sent.

Own tables in crm.db (created if missing, so the daily CRM backup covers them); the enquiries themselves stay in
the order package and are never changed. A row exists only after the first action; no row means «new».
`connect` is db.connect (or sqlite3 in tests): a context manager that commits.
"""
import time

NEW, IN_WORK, STOPPED, CLIENT = 'new', 'in_work', 'stopped', 'client'
STATUSES = (NEW, IN_WORK, STOPPED, CLIENT)
SCHEMA = (
    'CREATE TABLE IF NOT EXISTS lead_desk (order_id INTEGER PRIMARY KEY, status TEXT NOT NULL, note TEXT, '
    'client_id INTEGER, changed_by INTEGER, changed_at INTEGER)',
    'CREATE TABLE IF NOT EXISTS lead_desk_reminders (order_id INTEGER NOT NULL, kind TEXT NOT NULL, '
    'sent_at INTEGER NOT NULL, PRIMARY KEY (order_id, kind))',
    'CREATE TABLE IF NOT EXISTS lead_desk_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
)


class Store:
    def __init__(self, connect, *, clock=time.time):
        self.connect, self.clock = connect, clock

    def initialize(self):
        """Create the tables; the first start fixes the moment deadlines start to count (older enquiries: none)."""
        with self.connect() as c:
            for statement in SCHEMA:
                c.execute(statement)
            c.execute('INSERT OR IGNORE INTO lead_desk_meta (key, value) VALUES (?, ?)',
                      ('track_from', str(int(self.clock()))))

    def track_from(self):
        with self.connect() as c:
            row = c.execute("SELECT value FROM lead_desk_meta WHERE key='track_from'").fetchone()
        return int(row[0])

    def get(self, order_id):
        with self.connect() as c:
            row = c.execute('SELECT status, note, client_id FROM lead_desk WHERE order_id=?', (order_id,)).fetchone()
        return {'status': row[0], 'note': row[1] or '', 'client_id': row[2]} if row else \
            {'status': NEW, 'note': '', 'client_id': None}

    def many(self, order_ids):
        return {order_id: self.get(order_id) for order_id in order_ids}

    def _upsert(self, order_id, actor, column, value):
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO lead_desk (order_id, status) VALUES (?, ?)', (order_id, NEW))
            c.execute('UPDATE lead_desk SET %s=?, changed_by=?, changed_at=? WHERE order_id=?' % column,
                      (value, actor, int(self.clock()), order_id))

    def set_status(self, order_id, status, actor):
        if status not in STATUSES:
            raise ValueError('status')
        self._upsert(order_id, actor, 'status', status)

    def set_note(self, order_id, note, actor):
        self._upsert(order_id, actor, 'note', note.strip()[:1000])

    def set_client(self, order_id, client_id, actor):
        self._upsert(order_id, actor, 'client_id', int(client_id))
        self.set_status(order_id, CLIENT, actor)

    def claim_reminder(self, order_id, kind):
        """True once per enquiry and kind: the caller sends the reminder only then."""
        with self.connect() as c:
            cursor = c.execute('INSERT OR IGNORE INTO lead_desk_reminders (order_id, kind, sent_at) VALUES (?, ?, ?)',
                               (order_id, kind, int(self.clock())))
            return cursor.rowcount == 1
