"""Short order-storage outages are not sent as «Ошибка в боте» (BOT-ORDER-STORAGE-001, owner 2026-11-14)."""
PREVIEW_TASK = 'ORDER-GUARD-PREFLIGHT-20261114-R2'  # INSTALL-20261114 refused at intake: storage probe older than 15 min
INSTALL_TASK = 'ORDER-GUARD-INSTALL-20261114-R2'
PACKAGE = 'cloud/order_storage_guard_001'
NEW_MODULES = ('ua_order/outbox_guard.py',)
