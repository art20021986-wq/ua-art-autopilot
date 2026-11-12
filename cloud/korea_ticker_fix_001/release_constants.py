"""Korea ticker fix (TICKER-FIX-001, owner 2026-11-12: the score legend must be on the site now): collector update."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'TICKER-FIX-PREFLIGHT-20261112'
INSTALL_TASK = 'TICKER-FIX-INSTALL-20261112'
PACKAGE = 'cloud/korea_ticker_fix_001'
