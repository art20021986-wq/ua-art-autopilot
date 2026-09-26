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
DELIVERY_STATUS_STATUS: PREVIEW_PASSED_INSTALL_AUTHORIZED_PENDING_LAUNCH
DELIVERY_STATUS_CHECKPOINT: 2026-09-26 20:07 UTC — main Actions preview 36267876577 PASS, exact current plan 67279c4ec97fd9652db7af262562c3d0dd54e38b35d8f6651b539980a0cf4a66. Server calculation used 1.689 CPU seconds; allowed bounded operation at elevated CPU usage, no heavy media rebuild.
DELIVERY_STATUS_COUNTS: korea=4; ferry=4; georgia=6; kyiv=5; active total=19. Two archived rows project to hidden.
DELIVERY_STATUS_INSTALL_SCOPE: Eleven runtime Python files, two catalog pages, two home pages. Preserve all CRM rows and 112 protected files. Backup, conditional rollback, publication/worker/SQLite locks, bot pause/resume, health checks and transaction watchdog retained.
DELIVERY_STATUS_TESTS: 10 deployment recovery/transport tests; 7 policy and 10 SQLite migration tests. Prior live source integration run 36266189044: 39 tests and 8 actual golden template checks PASS.
DELIVERY_STATUS_SQL: Safe migration remains supplied and tested; this code/catalog transaction does not execute SQL against the CRM. Existing stored statuses are hidden by the runtime projection.
DELIVERY_STATUS_PENDING: Launch tasks/requests/DELIVERY-STATUS-INSTALL-20260927.json by its exact approval-bound marker, verify actual installation receipt and public catalog counts, then update this checkpoint. Do not declare production completion before receipt.
DELIVERY_STATUS_PRODUCTION_TOUCHED: NO live source, HTML, CRM row or bot changes yet. Preview uploaded a private candidate package and created/removed one isolated temporary task through Actions.
DELIVERY_STATUS_CONTINUATION: Existing automation 6ab80e71aa688191868f657b5631fcae remains enabled. Check current transaction before any next attempt; disable after verified runtime completion. No repeat owner approval for this scope.
DELIVERY_STATUS_FULL_ACCEPTANCE: NO
