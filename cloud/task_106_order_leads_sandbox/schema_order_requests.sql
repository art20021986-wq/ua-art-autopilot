PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS order_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_number TEXT UNIQUE,
    request_id TEXT NOT NULL UNIQUE,
    client_id INTEGER NOT NULL,
    source_event_id TEXT,
    source_channel TEXT NOT NULL CHECK (source_channel IN ('site', 'telegram_bot', 'whatsapp', 'manager')),
    source_url TEXT,
    lang TEXT NOT NULL CHECK (lang IN ('uk', 'ru', 'ka')),
    order_country_code TEXT NOT NULL CHECK (order_country_code IN ('korea', 'japan', 'usa', 'europe', 'china', 'canada', 'uae', 'georgia')),
    order_country_label TEXT,
    requested_model TEXT,
    other_model TEXT,
    vehicle_type TEXT,
    budget_bucket TEXT NOT NULL,
    budget_min INTEGER,
    budget_max INTEGER,
    currency TEXT NOT NULL DEFAULT 'USD',
    delivery_country TEXT NOT NULL,
    delivery_city TEXT NOT NULL,
    current_country TEXT,
    current_city TEXT,
    comment TEXT,
    contact_preference TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    responsible INTEGER,
    next_contact_at TEXT,
    converted_car_id INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT,
    FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_order_requests_source_event
ON order_requests(source_event_id)
WHERE source_event_id IS NOT NULL AND source_event_id <> '';

CREATE INDEX IF NOT EXISTS ix_order_requests_client ON order_requests(client_id);
CREATE INDEX IF NOT EXISTS ix_order_requests_status ON order_requests(status);
CREATE INDEX IF NOT EXISTS ix_order_requests_created ON order_requests(created_at);
CREATE INDEX IF NOT EXISTS ix_order_requests_delivery_city ON order_requests(delivery_city);
CREATE INDEX IF NOT EXISTS ix_order_requests_country ON order_requests(order_country_code);

