"""Card publication repair (CARD-SYNC-FIX-001); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'CARD-SYNC-FIX-PREFLIGHT-20261103-R2'  # R1 PASS; fresh storage measurement after FINANCE-INSTALL
INSTALL_TASK = 'CARD-SYNC-FIX-INSTALL-20261103'
PACKAGE = 'cloud/card_sync_fix_001'
