# Task 089 — CRM voice, photo opening and container stage repair

Status: **PASS — installed in production**

Deployment time: 2026-08-29 10:34 UTC  
Controlled restart: one restart; PythonAnywhere always-on state returned to `Running`  
Backup: `/home/Carix/backups/task_089_crm_voice_photo_repair/20260829T103444Z`

## Confirmed root causes

- Voice mileage parsing required an explicit `км/km` suffix and missed natural RU/UK forms.
- The voice handler loaded an undefined `override` name and required correction words before overwriting a named field.
- Card opening awaited sequential media delivery before showing the card and had no overall media deadline.
- The early `Загружено в контейнер` callback sent an optional Telegram prompt before the authoritative status write.
- Three high-frequency background jobs created avoidable scheduler and log pressure.

## Installed repair

- Natural mileage parsing for RU/UK digits, thousands, number words and `k`, always stored in `mileage_km`.
- Explicitly named voice fields can overwrite their existing value; the undefined name is removed; the existing killable STT watchdog remains enabled.
- Card text and controls are sent first. Photos and videos use bounded timeouts; an individual stale Telegram file cannot block the card.
- `sea_loaded` and `sea_transit` are written and read back before any Telegram network request.
- Guard heartbeat interval is 5 seconds, media spool interval is 2 seconds, and APScheduler success spam is suppressed without hiding warnings.

The handlers are global, so the repair applies to all existing and future CRM cards without a data migration.

## Evidence

- Exact live preimage hashes matched all five expected files before installation.
- Atomic installer validation: 15/15 checks PASS.
- Six RU/UK mileage cases PASS, including `пробег 48000`, `пробіг 48 тисяч`, word-form mileage and mileage without `км`.
- In-memory stage test: `write → answer → reply`; saved status `sea_loaded`.
- In-memory card test: card text precedes photos and videos.
- Slow-media test returned in 4.004 seconds instead of hanging.
- Post-restart heartbeat ages: client 0.290 seconds, CRM 3.110 seconds; active operations: 0.
- Final postcheck made no CRM database or media writes.

Rollback command:

```bash
python3.10 /home/Carix/autopilot_inbox/cloud/task_089_crm_voice_photo_repair/repair_installer.py rollback --backup /home/Carix/backups/task_089_crm_voice_photo_repair/20260829T103444Z
```
