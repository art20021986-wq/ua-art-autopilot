"""CRM self-check only in the bot process, error tail and one retry (PAGES-LAG-FIX-001, coordinator 2026-11-25)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'PAGES-LAG-FIX-PREFLIGHT-20261125-R2'  # R1 run 45594994898 PASS; R2: fresh preview for the install
INSTALL_TASK = 'PAGES-LAG-FIX-INSTALL-20261125'
PACKAGE = 'cloud/pages_lag_fix_001'
NEW_MODULES = ()
