"""Version 1 schema for the dedicated MySQL enquiry database only."""
TABLES = {
    'order_schema', 'order_requests', 'order_events', 'order_outbox',
    'order_drafts', 'order_notification_receipts',
}
DDL = (
    '''CREATE TABLE order_requests (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        request_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
        owner VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        payload_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        payload TEXT NOT NULL, channel VARCHAR(32) NOT NULL, created_at BIGINT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin''',
    '''CREATE TABLE order_events (
        event VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
        request_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        FOREIGN KEY (request_id) REFERENCES order_requests(request_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin''',
    '''CREATE TABLE order_outbox (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        request_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
        state VARCHAR(16) NOT NULL DEFAULT 'pending', attempts INT NOT NULL DEFAULT 0,
        available_at BIGINT NOT NULL, lease CHAR(32), lease_until BIGINT,
        INDEX order_outbox_due (state, available_at),
        FOREIGN KEY (request_id) REFERENCES order_requests(request_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin''',
    '''CREATE TABLE order_drafts (
        token_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
        owner VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        payload TEXT NOT NULL, expires_at BIGINT NOT NULL,
        telegram_owner VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin,
        INDEX order_drafts_expiry (expires_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin''',
    '''CREATE TABLE order_notification_receipts (
        request_id CHAR(36) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        recipient BIGINT NOT NULL, sent_at BIGINT NOT NULL,
        PRIMARY KEY (request_id, recipient),
        FOREIGN KEY (request_id) REFERENCES order_requests(request_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin''',
    '''CREATE TABLE order_schema (
        name VARCHAR(32) PRIMARY KEY, version INT NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin''',
)
