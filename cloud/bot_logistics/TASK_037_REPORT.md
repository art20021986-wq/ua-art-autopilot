# TASK 037 — BOT-LOGISTICS-001 Phase A Report

MEMORY_VERSION_READ: 4
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c

## 1. Honest scope statement

This Claude/Cloud worker has **no filesystem or network access to PythonAnywhere**. It can only read and write files inside this GitHub repository. Section 1 of task_037 ("Read-only production discovery probe") requires reading exact content from `/home/Carix/cars_ui.py`, `/home/Carix/team_bot.py`, `/home/Carix/avtoperedacha.py`, `/home/Carix/db.py`, `/home/Carix/run_all.py`, `/home/Carix/start_safe.py`, and `/home/Carix/crm.db`. None of these were reachable from this environment.

Per the task's own explicit fallback instruction:

> "If exact anchors/schema are unavailable without PythonAnywhere discovery, return `WAITING_PYTHONANYWHERE_READ_ONLY_DISCOVERY` with exactly one safe file and one command. Never invent PASS."

This report follows that instruction. **No PASS is invented. No `UA0006_CONTAINER_STATUS` is claimed.**

## 2. Requested single file + single command

- Safe file: `/home/Carix/crm.db`
- Command:

```
python3 cloud/bot_logistics/bot_logistics_discovery.py --db /home/Carix/crm.db --source /home/Carix/cars_ui.py --source /home/Carix/team_bot.py --source /home/Carix/avtoperedacha.py --source /home/Carix/db.py --source /home/Carix/run_all.py --source /home/Carix/start_safe.py
```

This must be executed by whoever controls the whitelisted, read-only "safe inbox" channel to PythonAnywhere (per canonical shared memory REC-0002/REC-0003, safe-inbox read-only sync is permitted; it is not production-write permission). The sanitized stdout output of that command (SHA-256 hashes, bounded anchor snippets, `UA0006_CONTAINER_STATUS`) should be fed back into the next round of this task so Phase A discovery can be completed and Gate A/Gate B candidates can be built against the *real* anchors.

## 3. What was delivered in this round (fully offline, fully verifiable)

| Deliverable | Status |
|---|---|
| `bot_logistics_discovery.py` | Written, NOT executed (no PythonAnywhere access) |
| `bot_logistics_transform.py` | Written; pure business logic + generic transform primitives, fully unit-testable |
| `bot_logistics_gate_b.py` | Written; `run_gate_b()` always refuses in Phase A; sub-primitives (manifest, backup, atomic replace, single-row update, read-back) are individually testable against fixtures |
| `test_bot_logistics.py` | Written; runs entirely offline against a fixture SQLite DB and fake Telegram menu objects |

### Container decision proven offline

`ONEYSELGF1046602` (16 alphanumeric chars) is proven by `test_container_ONEYSELGF1046602_accepted_intact` to pass the canonical validator (`normalize_container`), which enforces trim+uppercase, alphanumeric-only, 7–32 length, no internal whitespace, no control characters — and explicitly does **not** require a 4-letter+7-digit shape. This is a logic-level guarantee only; it does not by itself prove what is currently stored in the real `crm.db` for UA-0006.

### Canonical UX proven offline

- Exactly one `🚢 Этапы и доставка` button in the candidate main menu and exactly one in the candidate card editor (tests: `test_main_menu_has_exactly_one_hub_entry`, `test_card_editor_has_exactly_one_hub_entry`).
- Both route to the same `logi:hub:{ua_id}` callback (`test_both_entries_use_same_hub_callback_prefix`).
- Old duplicate labels (`Срок доставки`, `Номер и дата контейнера`, `Дней до прибытия`, `Номер контейнера`) are absent from the candidate menus (`test_old_duplicate_entries_absent_from_old_menus`).
- Hub renders stage/container/departure date/days/ETA from fresh values, with `render_field(None) == 'не указано'` — never fabricated (`test_eta_missing_inputs_render_not_specified`).
- Context-correct Back navigation proven for both entry contexts.
- Callback data length (<=64 bytes) and uniqueness proven.

### Persistence behavior proven offline against a fixture SQLite DB

- Exact single-row update + exact read-back (`test_exact_single_row_update_and_readback`).
- Idempotent same-value update (`test_same_value_update_is_idempotent`).
- Refusal + full-DB-unchanged on missing/ambiguous row, never a false success (`test_rollback_on_missing_row_never_reports_success`).
- `quick_check` before and after (`test_quick_check_before_and_after`).
- UA-0001..UA-0008 fixture rows unchanged except the one explicitly allowed UA-0006 container field (`test_ua_0001_to_0008_unchanged_except_allowed_ua0006`).
- UA-0009 fixture row proven byte-identical before/after and never published by any code path in this suite (`test_ua_0009_preserved_and_not_published`).
- Field preservation on stage-only and container-only edits.
- Deterministic ETA (`test_deterministic_eta`).
- Candidate transform compiles (`test_candidates_compile`) and 10 repeated applications yield identical hashes from the 2nd application onward (`test_ten_transforms_identical_hashes`).
- Backup/manifest build, tamper detection, and rollback-from-backup proven on synthetic files (`test_backup_manifest_and_tamper_detection`); SQLite backup-API consistency proven on the fixture DB (`test_sqlite_consistent_backup`).
- `run_gate_b()` proven to always refuse in this phase (`test_gate_b_run_is_disabled_in_phase_a`).
- No `send_photo`/`send_video`/`send_media_group`/`send_document` tokens present in the transform module (`test_no_photo_video_calls_in_transform_module`).
- No function in this suite returns anything beyond booleans/hashes/bounded fixture-only fields — no PII, tokens, or other-row values are ever printed.

## 4. UA-0009 conclusion (mandatory)

- UA-0009's fixture record is proven byte-identical before and after every persistence test in this suite.
- No code path in this Phase A package publishes, mass-regenerates, or otherwise touches any real UA-0009 card or DB row.
- The candidate hub design (`LogisticsRecord`, `build_hub_menu`, `cb_hub`, etc.) is fully UA-ID-agnostic — it takes `ua_id` as a plain string parameter throughout, with no UA-0006 or UA-0009 hardcoding anywhere in `bot_logistics_transform.py`. It is therefore structurally universal for UA-0009 and any future UA-XXXX card, **once applied to real, discovery-confirmed source anchors**.
- Per canonical shared memory, `ua0009_safe_to_publish` remains `NO`, and this report does **not** claim `UA_0009_READY: YES`. Complete proof would require real Gate A discovery evidence and a verified Gate B dry run against the real system, neither of which occurred here.

## 5. Markers

```
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

## 6. Outcome

```
WAITING_PYTHONANYWHERE_READ_ONLY_DISCOVERY
SAFE_FILE: /home/Carix/crm.db
COMMAND: python3 cloud/bot_logistics/bot_logistics_discovery.py --db /home/Carix/crm.db --source /home/Carix/cars_ui.py --source /home/Carix/team_bot.py --source /home/Carix/avtoperedacha.py --source /home/Carix/db.py --source /home/Carix/run_all.py --source /home/Carix/start_safe.py
```

Once that command's sanitized output is supplied back into this task, the next round can finalize real anchor-based `bot_logistics_transform.py` patches, complete Gate A with real evidence, and only then request the single CRITICAL owner approval for Gate B.
