"""Orders with a signed contract (LEAD-FOLDERS-001): created from a lead in the client bot, kept to delivery in the
CRM bot. Own tables in crm.db (created if missing, covered by the daily CRM backup); existing client cards are not
touched. An order keeps where its lead came from (the same folders), the contract number and file, and every stage
with who marked it and when.
`connect` is db.connect (or sqlite3 in tests): a context manager that commits.
"""
import time

STAGES = (('contract', 'Договор подписан'), ('bought', 'Авто выкуплено'), ('transit', 'В пути'),
          ('georgia', 'В Грузии'), ('ukraine', 'В Украине'), ('delivered', 'Выдано клиенту'))
STAGE_LABELS = dict(STAGES)
STAGE_KEYS = tuple(key for key, _ in STAGES)
FIELDS = ('lead_key', 'folder', 'contract_no', 'contract_file', 'name', 'phone', 'telegram', 'subject', 'source')
SCHEMA = (
    'CREATE TABLE IF NOT EXISTS crm_orders (id INTEGER PRIMARY KEY AUTOINCREMENT, lead_key TEXT NOT NULL UNIQUE, '
    'folder TEXT NOT NULL, contract_no TEXT NOT NULL, contract_file TEXT NOT NULL, name TEXT, phone TEXT, '
    'telegram TEXT, subject TEXT, source TEXT, stage TEXT NOT NULL, note TEXT, created_by INTEGER, '
    'created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)',
    'CREATE TABLE IF NOT EXISTS crm_order_stages (order_id INTEGER NOT NULL, stage TEXT NOT NULL, '
    'done_by INTEGER, done_at INTEGER NOT NULL, PRIMARY KEY (order_id, stage))',
    'CREATE INDEX IF NOT EXISTS idx_crm_orders_folder ON crm_orders(folder)',
)
COLUMNS = ('id',) + FIELDS + ('stage', 'note', 'created_by', 'created_at', 'updated_at')


def next_stage(stage):
    index = STAGE_KEYS.index(stage)
    return STAGE_KEYS[index + 1] if index + 1 < len(STAGE_KEYS) else None


class OrderBook:
    def __init__(self, connect, *, clock=time.time):
        self.connect, self.clock = connect, clock

    def initialize(self):
        with self.connect() as c:
            for statement in SCHEMA:
                c.execute(statement)

    def create(self, values, actor):
        """The order of a lead (idempotent by the lead: a repeated call returns the same order id)."""
        if set(values) != set(FIELDS) or not values['contract_no'].strip() or not values['contract_file']:
            raise ValueError('order')
        now = int(self.clock())
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO crm_orders (%s, stage, created_by, created_at, updated_at) '
                      'VALUES (%s, ?, ?, ?, ?)' % (', '.join(FIELDS), ', '.join('?' * len(FIELDS))),
                      tuple(values[f] for f in FIELDS) + ('contract', actor, now, now))
            order_id = c.execute('SELECT id FROM crm_orders WHERE lead_key=?', (values['lead_key'],)).fetchone()[0]
            c.execute('INSERT OR IGNORE INTO crm_order_stages (order_id, stage, done_by, done_at) VALUES (?, ?, ?, ?)',
                      (order_id, 'contract', actor, now))
        return order_id

    def _rows(self, where='', args=()):
        with self.connect() as c:
            rows = c.execute('SELECT %s FROM crm_orders %s ORDER BY id DESC' % (', '.join(COLUMNS), where), args).fetchall()
        return [dict(zip(COLUMNS, row)) for row in rows]

    def in_folder(self, folder):
        return self._rows('WHERE folder=?', (folder,))

    def all(self):
        return self._rows()

    def get(self, order_id):
        rows = self._rows('WHERE id=?', (int(order_id),))
        if not rows:
            raise LookupError('order')
        with self.connect() as c:
            done = c.execute('SELECT stage, done_at FROM crm_order_stages WHERE order_id=?', (int(order_id),)).fetchall()
        return {**rows[0], 'stages': {stage: at for stage, at in done}}

    def advance(self, order_id, expected, actor):
        """Mark the next stage; `expected` is the stage the person saw, so a double tap marks it once."""
        order = self.get(order_id)
        following = next_stage(order['stage'])
        if order['stage'] != expected or following is None:
            return order
        now = int(self.clock())
        with self.connect() as c:
            c.execute('UPDATE crm_orders SET stage=?, updated_at=? WHERE id=? AND stage=?',
                      (following, now, order['id'], expected))
            c.execute('INSERT OR IGNORE INTO crm_order_stages (order_id, stage, done_by, done_at) VALUES (?, ?, ?, ?)',
                      (order['id'], following, actor, now))
        return self.get(order_id)

    def set_note(self, order_id, note):
        with self.connect() as c:
            c.execute('UPDATE crm_orders SET note=?, updated_at=? WHERE id=?',
                      (note.strip()[:1000], int(self.clock()), int(order_id)))
