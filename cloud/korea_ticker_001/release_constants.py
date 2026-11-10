"""The home ticker comes alive: an hourly server job collects tomorrow's Korea lots (JPAUTO-KOREA-001, owner «Да» to Б)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'KOREA-TICKER-PREFLIGHT-20261110-R2'
INSTALL_TASK = 'KOREA-TICKER-INSTALL-20261110'
PACKAGE = 'cloud/korea_ticker_001'
