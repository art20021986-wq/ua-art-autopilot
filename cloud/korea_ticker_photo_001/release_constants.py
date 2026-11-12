"""Korea ticker light photos (TICKER-PHOTO-001, owner 2026-11-12: ticker photos load slowly; one main photo is enough)."""
# One place for the task names: make_release.py writes the requests, the controller accepts only these.
PREVIEW_TASK = 'TICKER-PHOTO-PREFLIGHT-20261112-R3'  # R2 storage stale at intake (24 min); install right after
INSTALL_TASK = 'TICKER-PHOTO-INSTALL-20261112-R2'  # R1 refused at intake: STORAGE_PROBE_STALE_OR_FUTURE (nothing written)
PACKAGE = 'cloud/korea_ticker_photo_001'
