"""Korea ticker fix 4 (TICKER-FIX4-001, owner 2026-11-12): the search posts the default-checked boxes (the auction lists
lots again), and the ticker shows today's and the next auction day's counts."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'TICKER-FIX4-PREFLIGHT-20261112'
INSTALL_TASK = 'TICKER-FIX4-INSTALL-20261112'
PACKAGE = 'cloud/korea_ticker_fix4_001'
