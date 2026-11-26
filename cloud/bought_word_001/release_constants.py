"""BOUGHT-WORD-001: «проверенные» removed from the «выкуплено» stage texts (owner 2026-11-26, via coordinator)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'BOUGHT-WORD-PREFLIGHT-20261126-R2'  # R1 PASS run 45765997922; R2: fresh storage probe for the install
INSTALL_TASK = 'BOUGHT-WORD-INSTALL-20261126'
PACKAGE = 'cloud/bought_word_001'
NEW_MODULES = ()
