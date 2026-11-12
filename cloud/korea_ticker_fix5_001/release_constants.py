"""Korea ticker fix 5 (TICKER-FIX5-001, owner 2026-11-12): ten times more auction cars, original photos, photo-copy
failures logged."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'TICKER-FIX5-PREFLIGHT-20261112-R2'  # owner: popular models only; run the ticker job right after the install
INSTALL_TASK = 'TICKER-FIX5-INSTALL-20261112'
PACKAGE = 'cloud/korea_ticker_fix5_001'
