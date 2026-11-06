"""Work state of leads in the CRM database (LEAD-FOLDERS-001): status, manager note, reminders sent.

A lead is named by a text key from ua_lead_sources ('or:<id>' for an order package enquiry, 'bot:<hash>' for a
client bot enquiry); the enquiries themselves are never changed. Own tables in crm.db (created if missing, so the
daily CRM backup covers them). A row exists only after the first action; no row means «new». The moment deadlines
start to count stays in lead_desk_meta (ORDER-PROCESS-001), so it survives this release.
`connect` is db.connect (or sqlite3 in tests): a context manager that commits.
"""
import time

NEW, IN_WORK, STOPPED, CONTRACT = 'new', 'in_work', 'stopped', 'contract'
STATUSES = (NEW, IN_WORK, STOPPED, CONTRACT)
SCHEMA = (
    'CREATE TABLE IF NOT EXISTS lead_state (lead_key TEXT PRIMARY KEY, status TEXT NOT NULL, note TEXT, '
    'changed_by INTEGER, changed_at INTEGER)',
    'CREATE TABLE IF NOT EXISTS lead_state_reminders (lead_key TEXT NOT NULL, kind TEXT NOT NULL, '
    'sent_at INTEGER NOT NULL, PRIMARY KEY (lead_key, kind))',
    'CREATE TABLE IF NOT EXISTS lead_desk_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
)


class Store:
    def __init__(self, connect, *, clock=time.time):
        self.connect, self.clock = connect, clock

    def initialize(self):
        with self.connect() as c:
            for statement in SCHEMA:
                c.execute(statement)
            c.execute('INSERT OR IGNORE INTO lead_desk_meta (key, value) VALUES (?, ?)',
                      ('track_from', str(int(self.clock()))))

    def track_from(self):
        with self.connect() as c:
            return int(c.execute("SELECT value FROM lead_desk_meta WHERE key='track_from'").fetchone()[0])

    def all(self):
        """{lead_key: {'status', 'note'}} for every lead with a row."""
        with self.connect() as c:
            rows = c.execute('SELECT lead_key, status, note FROM lead_state').fetchall()
        return {row[0]: {'status': row[1], 'note': row[2] or ''} for row in rows}

    def get(self, key):
        return self.all().get(key) or {'status': NEW, 'note': ''}

    def _upsert(self, key, actor, column, value):
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO lead_state (lead_key, status) VALUES (?, ?)', (key, NEW))
            c.execute('UPDATE lead_state SET %s=?, changed_by=?, changed_at=? WHERE lead_key=?' % column,
                      (value, actor, int(self.clock()), key))

    def set_status(self, key, status, actor):
        if status not in STATUSES:
            raise ValueError('status')
        self._upsert(key, actor, 'status', status)

    def set_note(self, key, note, actor):
        self._upsert(key, actor, 'note', note.strip()[:1000])

    def claim_reminder(self, key, kind):
        """True once per lead and kind: the caller sends the reminder only then."""
        with self.connect() as c:
            cursor = c.execute('INSERT OR IGNORE INTO lead_state_reminders (lead_key, kind, sent_at) VALUES (?, ?, ?)',
                               (key, kind, int(self.clock())))
            return cursor.rowcount == 1
