# TASK088 price synchronization and autopilot integration

**Implemented and locally tested candidate; not installed or activated.** The owner authorized execution and asked to finish without further sequential questions. No new archive or repeated approval is requested.

Stages 1 and 2 are canonically FINISHED. This package preserves their schema, existing prices and independent editing. Stages 3 and 4 still require deployment and real acceptance.

## Package

| Component | Implemented role |
| --- | --- |
| outbox.py | Same-transaction durable intent, stable identity, revisions, claims, STOP and verified recovery. |
| patch_cars_ui.py | Exact-source hook for both price buttons, other price input, voice CAS/undo and bootstrap. |
| uaart_price_sync_runtime.py | Price-only card/catalog updates, common lock, backup/journal, semantic acknowledgements, deadline, recovery and Telegram reports. |
| uaart_price_sync_binding.py | Actual authority, owner-chat facts, code/identity/path bindings, HALT and revocation; no guessed controls. |
| patch_guard.py | Fences the existing full-catalog publisher against unverified price changes. |
| install_package.py | Snapshot-bound installation, online backups, CAS, row/audit preservation and rollback. |
| preflight.py | Read-only server verification with private candidates and offline schema tests; no fabricated Gate B. |

The companion cloud/task088_stage3_renderer package patches both real generators and the final catalog guard. Initial migration touches only price fragments. catalog_design_golden.html stays unchanged.

## Owner rules preserved

- Both prices are independent USD values; no migration, conversion or cross-write.
- Ukraine includes delivery to Kyiv, Ukrainian customs and certification.
- Georgia includes delivery to AUTOPAPA, parking №16, without Georgian customs.
- Both prices appear in the card and catalog; missing Georgia price shows “Цена уточняется”.
- Published cars update after CRM saves. Initial publication remains manual.
- Failure stops the affected task. Committed CRM prices remain saved; stale changes cannot replay; recovery needs proven correction and fresh checks.
- Other tasks continue only after safety/resource checks.
- Telegram only: first failure alert to the verified private CRM-bot chat, then unresolved incidents only in the daily 10:00 Asia/Ho_Chi_Minh report. Ordinary approved task delay threshold: five minutes.

## Verified progress and current boundary

Complete current source, exact hashes, golden HTML, current UA-0010/catalog HTML and published-price rows were recovered read-only. The missing-source/archive blocker is resolved.

Root rerun: **136/136 price-sync tests PASS** and **40/40 renderer tests PASS**. These are local tests, not deployment or an operational percentage.

On PythonAnywhere, the obsolete TASK083 daily 08:02 installer row **1502679** was disabled; the UI now offers **Enable task**. CRM and the existing monitor stayed **Running**. No live source, CRM price or public HTML changed. This scheduler change is the concrete server action completed so far.

The remaining authority blocker is an authenticated fresh bridge to private-repository canonical control state. No valid local EXECUTION_MODE/AUTOPILOT_HALT mirror was found. Invented JSON or an approval boolean cannot replace real task/claim/transaction/Gate B evidence.

Next: assembled server preflight; verified control bridge; snapshot-bound install; real config/anchor; controlled activation; live CRM/card/catalog/Telegram acceptance. No additional owner approval is currently requested.

## Contracts and tests

See INSTALLER_CONTRACT.md, BINDING_CONTRACT.md and ../task088_autopilot_owner_policy/STAGE3_GATE_B_READINESS.md.

    python -B -m unittest discover -s cloud/task088_price_sync -p 'test_*.py' -v

Some tests require exact privately recovered fixtures. Do not put private source, CRM databases or preflight SQLite copies in public GitHub or public attachments. Code and local tests alone do not complete Stage 3/4.
