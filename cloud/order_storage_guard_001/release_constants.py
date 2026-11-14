"""Short order-storage outages are not sent as «Ошибка в боте» (BOT-ORDER-STORAGE-001, owner 2026-11-14)."""
PREVIEW_TASK = 'ORDER-GUARD-PREFLIGHT-20261114'
INSTALL_TASK = 'ORDER-GUARD-INSTALL-20261114'
PACKAGE = 'cloud/order_storage_guard_001'
NEW_MODULES = ('ua_order/outbox_guard.py',)
