"""Korea ticker fix 6 (TICKER-FIX6-001, owner 2026-11-12): the ticker takes auction cars from the next auction days
and today until it is full (a freshly listed next day may have no popular car with a photo and price yet), and the
waiting tile shows today's and the next auction day's counts."""

PREVIEW_TASK = 'TICKER-FIX6-PREFLIGHT-20261112-R2'  # R1 storage probe expired waiting for the owner's «да»
INSTALL_TASK = 'TICKER-FIX6-INSTALL-20261112-R2'
PACKAGE = 'cloud/korea_ticker_fix6_001'
