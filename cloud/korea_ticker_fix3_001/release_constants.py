"""Korea ticker fix 3 (TICKER-FIX3-001, owner 2026-11-12): with no lots listed the ticker still shows the legend tile."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'TICKER-FIX3-PREFLIGHT-20261112'
INSTALL_TASK = 'TICKER-FIX3-INSTALL-20261112'
PACKAGE = 'cloud/korea_ticker_fix3_001'
