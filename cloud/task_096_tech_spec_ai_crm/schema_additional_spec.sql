-- TASK 096 sandbox schema for "Дополнительная спецификация"
-- Apply ONLY to a sandbox copy of the CRM database. Never apply to production.
-- Primary CRM fields (operator-entered) are NEVER modified by this schema or by any
-- tool in this package. This schema only adds new, clearly separated tables.

PRAGMA foreign_keys = ON;

-- Registry of primary (operator-only) field keys per car, used purely as a read-only
-- reference list for dedup/protection checks. This table is populated once from a
-- read-only snapshot of the CRM's primary schema; it is never written to by AI or
-- indexation, and it never stores price data.
CREATE TABLE IF NOT EXISTS primary_field_registry (
    car_uid       TEXT NOT NULL,
    field_key     TEXT NOT NULL,
    normalized_value TEXT NOT NULL,
    PRIMARY KEY (car_uid, field_key)
);

-- Hard denylist of field keys/synonyms that must never be extracted or stored anywhere
-- in additional_specification, regardless of source.
CREATE TABLE IF NOT EXISTS price_denylist (
    denylist_key TEXT PRIMARY KEY
);

INSERT OR IGNORE INTO price_denylist (denylist_key) VALUES
    ('purchase_price'), ('cost_price'), ('auction_price'), ('wholesale_price'),
    ('dealer_price'), ('buy_price'), ('acquisition_price'), ('internal_price'),
    ('закупочная_цена'), ('оптовая_цена'), ('аукционная_цена'), ('себестоимость');

-- The additional specification block itself. Populated only by AI enrichment and by
-- site-indexation processes. Operator-entered primary fields remain in the CRM's
-- existing primary tables and are read-only from this pipeline's perspective.
CREATE TABLE IF NOT EXISTS additional_specification (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    car_uid           TEXT NOT NULL,                -- e.g. 'UA-0009'
    field_key         TEXT NOT NULL,                -- canonical technical key
    field_value       TEXT NOT NULL,
    normalized_value  TEXT NOT NULL,                -- lower-cased/trimmed for dedup
    source            TEXT NOT NULL CHECK (source IN ('AI','INDEXATION')),
    source_url        TEXT,                         -- internal technical reference only, never shown to clients
    confidence        REAL DEFAULT 0.0,
    is_price_field    INTEGER NOT NULL DEFAULT 0 CHECK (is_price_field = 0), -- hard-fixed to 0, enforced by app logic too
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (car_uid, field_key)                      -- one canonical value per key per car (no semantic dupes)
);

CREATE INDEX IF NOT EXISTS idx_addspec_car ON additional_specification (car_uid);
CREATE INDEX IF NOT EXISTS idx_addspec_key ON additional_specification (field_key);

-- Audit trail: every rejected write attempt (dedup collision, price field, manual-field
-- collision) is recorded here for transparency. No price values are ever stored, even
-- in rejection records.
CREATE TABLE IF NOT EXISTS additional_specification_rejections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    car_uid       TEXT NOT NULL,
    field_key     TEXT NOT NULL,
    reason        TEXT NOT NULL,   -- 'DUPLICATE' | 'MANUAL_FIELD_PROTECTED' | 'PRICE_FIELD_FORBIDDEN'
    rejected_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
