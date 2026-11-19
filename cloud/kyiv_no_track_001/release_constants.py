"""A car in Kyiv shows no container tracking (KYIV-NO-TRACK-001, owner 2026-11-19). R1 preview run 44471822187 PASS; R2 adds old Kyiv pages."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'KYIV-NO-TRACK-PREFLIGHT-20261119-R2'
INSTALL_TASK = 'KYIV-NO-TRACK-INSTALL-20261119'
PACKAGE = 'cloud/kyiv_no_track_001'
