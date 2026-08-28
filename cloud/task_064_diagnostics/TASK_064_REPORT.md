# TASK 064 — permanent diagnostics repair

status: PASS
generated_at_utc: 2026-08-28T17:00:57Z
published_cards: 10
production_files_changed: 49
crm_write: false
db_write: false
service_reload: false
rollback_attempted: false
backup_root: `/home/Carix/autopilot_inbox/cloud/task_064_diagnostics/backups/20260828T170058Z-530b345caf`
generator_sha256: `1522350ae821ffcde9393d10ac9707830a4592c2adcdf4ad0f666841f14b3656` → `530b345caf2534fe4c38dc0d3fc3ab69e01b4a540cf67fe012a6a7678a786453`

## Card matrix

- `UA-0001`: video PASS, site PASS, diagnostics links 1/1, empty state: NO
- `UA-0002`: video PASS, site PASS, diagnostics links 1/1, empty state: NO
- `UA-0003`: video PASS, site PASS, diagnostics links 1/1, empty state: YES
- `UA-0004`: video PASS, site PASS, diagnostics links 1/1, empty state: YES
- `UA-0005`: video PASS, site PASS, diagnostics links 1/1, empty state: YES
- `UA-0006`: video PASS, site PASS, diagnostics links 1/1, empty state: YES
- `UA-0007`: video PASS, site PASS, diagnostics links 1/1, empty state: YES
- `UA-0008`: video PASS, site PASS, diagnostics links 1/1, empty state: NO
- `UA-0009`: video PASS, site PASS, diagnostics links 1/1, empty state: YES
- `UA-0010`: video PASS, site PASS, diagnostics links 1/1, empty state: YES

The canonical generator now treats diagnostics as mandatory even with no
materials. Card writes and etalon writes can no longer overwrite `*-diag.html`.
Every current card has exactly one diagnostics link in both `/video` and `/site`.
