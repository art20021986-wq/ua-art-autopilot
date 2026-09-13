# Stages 3/4 readiness — 13 September 2026

Updated at 2026-09-13T16:50:46Z. **Execution is authorized. No archive or renewed approval is requested. Live installation and acceptance have not occurred.**

## Actual stage status

| Stage | Verified state | Remaining work |
| --- | --- | --- |
| 1 — independent price fields | Canonical FINISHED | Preserve existing fields and values; do not reinstall or migrate prices. |
| 2 — CRM input/readback | Canonical FINISHED/PASS; receipt closed 2026-09-13T05:56:14Z | Preserve accepted independent writes and restored original values. |
| 3 — website publication | Current-source implementation and local tests prepared; not installed | Server preflight, real installation, activation and public card/catalog acceptance. |
| 4 — reliable autopilot | Worker, recovery, notifications and authority provider implemented; not activated | Authenticated fresh control bridge, real authority, bootstrap and end-to-end acceptance. |

The Stage 2 [canonical receipt](https://github.com/art20021986-wq/ua-art-autopilot/blob/main/state/receipts/TASK088-GE-PRICE-CRM-STAGE2.json) permits Stage 3. Its identity must not be reused for a new install.

## Source recovery completed

Complete current source was recovered read-only from the authenticated server, privately, with exact byte hashes. It includes the CRM handler, both generators, final catalog guard, publication transaction guard, master publisher and stage synchronizer. Golden catalog HTML, actual UA-0010 HTML, the actual 18-car catalog and current published-price rows were also obtained.

Current cars_ui.py SHA256:
4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde.

The source confirms the original gap: the accepted Stage 2 helper saves the selected price and audit without a durable publication event. **No user-supplied archive is needed.** Earlier statements that complete source was unavailable are superseded. Private source and SQLite copies must not be published to GitHub.

## Implementation prepared

- Source-bound CRM hook: outbox event in the same price/audit transaction; both price buttons, text/AI/phrase routes, voice CAS and nullable Georgia-price undo; stale-delivery protection.
- Narrow patches for yadro.py, stranica.py and the final catalog_design_guard.py. Initial HTML migration changes only price fragments. Golden catalog stays read-only.
- Runtime: common publication lock, backup/journal, public semantic readback, STOP, 60-second deadline, retained committed CRM prices, verified recovery and Telegram reporting.
- Existing whole-catalog publisher receives a price-write fence. First vehicle publication stays manual.
- Installer: immutable plan/source/CRM/audit/schema checks, verified backups, quota, CAS and rollback preserving foreign changes. Installation evidence remains INSTALLED_PENDING_LIVE_ACCEPTANCE, not stage completion.

## Real server action completed

The obsolete PythonAnywhere **TASK083 daily 08:02 scheduled installer**, row **1502679**, was disabled under the owner's latest execution instruction. The authenticated UI now offers **Enable task**, confirming the disabled state. This removes an unattended writer that could reinstall old source outside the reviewed path.

CRM and the existing monitor remained **Running**. Working source files, CRM values and public HTML were not changed. This was a scheduler change; the whole session must not be described as read-only.

## Validation and remaining technical blocker

- Root rerun: **136/136 price-sync tests PASS**.
- Root renderer rerun: **40/40 tests PASS**.
- Real read-only server preflight: **not run yet**. The bundle now uses the corrected four-key stage-count map and stage2_receipt field.
- Actual card/catalog captures support candidate QA; they do not establish live publication or the production 60-second SLA.

No verified local mirror of canonical EXECUTION_MODE/AUTOPILOT_HALT was found on the server. A fresh authenticated bridge to the private repository's canonical control records, including revocation/HALT handling, must be established. Cached or invented JSON and a generic gate_b=true flag cannot replace this evidence.

Next: server preflight; complete the control bridge and concrete Gate B evidence; install against the verified snapshot; create the real config/anchor; activate under controlled conditions; verify CRM → card → catalog and Telegram.

These are implementation and evidence requirements, **not a new request for owner permission**. Do not label Stage 3/4 FINISHED or report active delivery/reliability gains until their real acceptance receipts exist.
