# BOT-LOGISTICS-001 — Phase A (task_037)

## Scope

This package implements Phase A only for a unified "🚢 Этапы и доставка" logistics hub inside BOT CRM:

- read-only PythonAnywhere discovery probe (script, NOT executed by this worker — no PythonAnywhere access from this environment);
- canonical hub design (container validation, ETA computation, single-entry-point UX contract);
- a candidate transform module that will only be applied to the *real* discovered source once Gate A discovery evidence exists;
- a prepared, fail-closed Gate B installer that is NOT executed;
- an offline test suite that runs entirely against synthetic fixtures (temp dirs, fixture SQLite, fake Telegram UI objects) — no network, no `/home/Carix`.

## Why this is WAITING_PYTHONANYWHERE_READ_ONLY_DISCOVERY

This Claude/Cloud worker has **no filesystem or network access to PythonAnywhere**. It can only read/write inside this GitHub repository. The task requires exact source anchors and SQLite schema evidence from `/home/Carix/*` (cars_ui.py, team_bot.py, avtoperedacha.py, db.py, run_all.py, start_safe.py, crm.db) before any real patch can be produced or verified against production reality.

Because those exact anchors are **not available** to this worker, per the task's own instruction ("If exact anchors/schema are unavailable without PythonAnywhere discovery, return `WAITING_PYTHONANYWHERE_READ_ONLY_DISCOVERY`"), this package:

- does **not** claim to have found real anchors;
- does **not** claim `UA0006_CONTAINER_STATUS` (that requires reading the real `crm.db`, which this worker cannot do);
- ships a discovery script that must be executed by whoever *does* have safe, whitelisted read-only access to PythonAnywhere (the "safe inbox" channel referenced in canonical shared memory), then the sanitized output fed back into this repo for the next round.

## Requested next step (single file + single command)

- Safe file: `/home/Carix/crm.db`
- Command:

```
python3 cloud/bot_logistics/bot_logistics_discovery.py --db /home/Carix/crm.db --source /home/Carix/cars_ui.py --source /home/Carix/team_bot.py --source /home/Carix/avtoperedacha.py --source /home/Carix/db.py --source /home/Carix/run_all.py --source /home/Carix/start_safe.py
```

This command is read-only (SQLite opened with `mode=ro` + `PRAGMA query_only=ON`, source files opened for read only), never recursive, never touches anything outside the exact whitelist, and prints only sanitized, bounded evidence (SHA-256 hashes, anchor line numbers/snippets, quick_check result, single UA-0006 container comparison against `ONEYSELGF1046602`, and `UA0006_CONTAINER_STATUS: ALREADY_CORRECT|NEEDS_EXACT_UPDATE`). It must never print any other row's data.

## What IS delivered and verifiable right now (offline)

- `bot_logistics_discovery.py` — the fail-closed, whitelist-only, read-only discovery probe (ready to run on PythonAnywhere, NOT run here).
- `bot_logistics_transform.py` — canonical, UA-ID-agnostic hub logic: container normalization/validation, ETA computation, patch-application primitives operating on anchor patterns. Includes a deterministic "apply N times → identical hash" guarantee.
- `bot_logistics_gate_b.py` — prepared, NOT executed installer skeleton. Refuses to run without a matching discovery manifest; ends `WAITING_OWNER_APPROVAL` by design; never restarts processes.
- `test_bot_logistics.py` — offline pytest suite covering container validation, ETA determinism, idempotent transform hashing, fixture-SQLite update/read-back/rollback, menu single-entry-point checks, callback_data length/uniqueness, UA-0001..UA-0009 non-interference on fixture data, and Gate B fail-closed refusal logic. Runs with `pytest -q cloud/bot_logistics/test_bot_logistics.py` — no network, no `/home/Carix`.

## What is explicitly NOT claimed

- No claim that any real BOT CRM source file was read.
- No claim about the real UA-0006 container value in the real `crm.db`.
- No claim of `UA_0009_READY: YES`.
- No production, CRM, or real-DB write of any kind.
