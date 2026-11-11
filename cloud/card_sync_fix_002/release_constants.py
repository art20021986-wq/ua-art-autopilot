"""Card publication repair after SOCIAL-LINKS-001 (CARD-SYNC-FIX-002); no private source in this package."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'CARD-SYNC-FIX2-PREFLIGHT-20261110-R3'  # R2 PASS; its install run was cancelled by a concurrent launch
INSTALL_TASK = 'CARD-SYNC-FIX2-INSTALL-20261111-R2'  # 20261110 consumed, its run cancelled (nothing written)
PACKAGE = 'cloud/card_sync_fix_002'
