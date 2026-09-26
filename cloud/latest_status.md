TASK_ID: UA-ART-CRM-SITE-CONSISTENCY-001
STATUS: BLOCKED_CPU_QUOTA_AND_PENDING_FULL_REHEARSAL
OWNER_INSTRUCTION: 2026-09-26 — critical production repair and prevention authorized; repeated approval is not needed for this scope, required gates remain mandatory.
PRODUCTION_INSTALLATION_STARTED: NO
PRODUCTION_SOURCE_HTML_CRM_WRITTEN_BY_THIS_TASK: NO
FULL_ACCEPTANCE: NO
GATE_B: NOT_READY
RESOURCE_BLOCKER: CPU 5023.208252 / 5000 seconds (100.464%) at 16:16 UTC. CLAUDE.md requires heavy operations deferred at >=85%. Next quota reset 2026-09-27 08:37:11 UTC. Recheck actual usage before any heavy action.
CANDIDATE: CRM-ordered visible photos and cover; immutable cover URLs; revisions include actual sidecar specs/visibility/bindings, car/media/download ledger; prepublication final-card validation; stronger public freshness checks.
SOURCE_DETAIL: Actual specification database is vin_specs_task111_v3.db, not legacy additional_specification in crm.db.
LOCAL_TESTS: 55 PASS in clean pinned-package layout; execution-contract inspection PASS.
LIVE_READONLY_CORE: 21/21 existing server card HTML match CRM identity, VIN, mileage, engine, fuel, gearbox, drive and color. Not proof of media correctness or full acceptance.
KNOWN_PHOTO_MISMATCHES: UA-0017/040.jpg and UA-0019/001.jpg are hidden in CRM but currently published. Candidate not installed.
LAST_SHADOW_RUN: 36254742734 FAIL, original protected files unchanged, actual stale-mileage adapter rejection PASS. First-card VIN selector assumed short table; corrected to explicitly check dedicated visible VIN block and any table VIN, with mismatch/duplicate tests. Full corrected rehearsal not run due CPU blocker.
BACKGROUND_REPAIR_RUNNING: NO after current bounded preview cleanup; no delayed deployment configured.
DATA_CONFLICT: UA-0022 condition_text says in transit while status is kr_bought; do not invent physical status.
NEXT: Check CPU, full shadow rehearsal, bounded backup/rollback rehearsal and exact production manifest/Gate B, CRITICAL main Actions installation, verified bot task restart, ordinary public/browser verification. Do not repeat obsolete GE-price audit.
CHECKPOINT: cloud/crm_site_consistency_001/CHECKPOINT.json
RESOURCE_EVIDENCE: cloud/crm_site_consistency_001/resource_blocker_20260926.json
CLAUDE_TAKEOVER: 2026-09-26 16:29 UTC — Claude принял передачу от Codex (владелец: «Запускай»). Локально 55/55 тестов PASS, execution-contract compile PASS. Тяжёлый шаг отложен до сброса CPU; продолжение запланировано на 2026-09-27 08:50 UTC (свежий замер CPU → shadow-прогон). Production не трогался.
NOTE_PRICE: public_fields.py не сверяет цену; исходная жалоба владельца — цена 21200 в CRM ≠ сайт (кеш скрипта цены, см. cloud/price_mismatch_20260926/diagnosis.md). Не входит в кандидат Codex — предложено отдельно.


DELIVERY_STATUS_TASK: UA-ART-DELIVERY-STATUS-001
DELIVERY_STATUS_STATUS: CANDIDATE_VALIDATED_INSTALLATION_DEFERRED_CPU
DELIVERY_STATUS_PR: #121 merged into main as 13e549228a77eb35ad72c9945a0e66d4da49798d; no production installation.
DELIVERY_STATUS_CHECKPOINT: 2026-09-26 18:27 UTC — STANDARD main Actions preflight 36262362403 SUCCESS; 27 tests against current pinned server source and 8 tests against actual golden HTML PASS. All 10 candidate modules built. No production source, HTML, CRM data, schedules or bot processes changed.
DELIVERY_STATUS_RESOURCE: Fresh authenticated GET cpu/ at 18:25:09 UTC: 6079.193945 / 5000 seconds (121.584%). Reset 2026-09-27 08:37:11 UTC / 15:37 Asia/Ho_Chi_Minh. CLAUDE.md defers heavy operations at >=85%.
DELIVERY_STATUS_PENDING: Prepare and rehearse bounded CRITICAL deployment adapter with backup/rollback/watchdog and writer exclusion; apply SQL only with verified backup; restart bot; verify normal publication, hidden/reactivated cars, both catalog copies and public counters. Preserve prices/VIN/photos. Do not combine with the consistency task transaction.
DELIVERY_STATUS_CONTINUATION: Automation "Завершить статусы CRM" enabled. Starts 2026-09-27 15:40 Asia/Ho_Chi_Minh, hourly up to 3 attempts; check fresh quota and active writers before work, disable after verified completion. Not currently installing. Original owner authorization remains sufficient.
DELIVERY_STATUS_EVIDENCE: cloud/delivery_status_001/preflight_evidence.json; cloud/delivery_status_001/CONTINUATION.json; state/receipts/DELIVERY-STATUS-PREFLIGHT-20260927.json. Preflight FINISHED is not production acceptance.
