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
DELIVERY_STATUS_STATUS: CANDIDATE_AND_SAFE_MIGRATION_VALIDATED_PRODUCTION_DEFERRED_CPU
DELIVERY_STATUS_PRS: #121 status policy; #122 safe SQLite migration/rollback; #123 fallback CRM menu; #124 bounded GET-only preflight error handling. All merged to main; no production installation.
DELIVERY_STATUS_CHECKPOINT: 2026-09-26 19:32 UTC — main Actions R4 preflight 36266189044 SUCCESS; 39 integration/migration tests and 8 actual-golden checks PASS. All 11 candidate modules built against current pinned source. Both CRM menus expose the four canonical statuses.
DELIVERY_STATUS_MIGRATION: status_migration.py takes and verifies a private SQLite backup under the writer lock; only removed statuses change; rollback checks affected rows and preserves unrelated edits. Ten real SQLite tests including WAL and concurrent-edit rejection PASS. Migration has not run on production.
DELIVERY_STATUS_RESOURCE: GET cpu/ at 19:29:57 UTC: 6647.962026 / 5000 seconds (132.959%). Reset 2026-09-27 08:37:11 UTC / 15:37 Asia/Ho_Chi_Minh. CLAUDE.md defers heavy actions at >=85%.
DELIVERY_STATUS_PENDING: Complete and rehearse bounded CRITICAL installer/lifecycle/manifest with backup/rollback/watchdog and writer exclusion; full publisher rehearsal, source installation, SQL, bot restart and live catalog/counter checks remain pending. The tested SQLite migrator alone is not a deployment. Do not combine with the consistency task transaction.
DELIVERY_STATUS_CONTINUATION: Existing automation "Завершить статусы CRM" confirmed enabled, starting 2026-09-27 15:40 Asia/Ho_Chi_Minh, hourly up to 3 attempts. Recheck CPU/source/active writers; disable after verified completion. Original owner authorization remains sufficient.
DELIVERY_STATUS_PRODUCTION_TOUCHED: NO — no source, HTML, CRM rows, schedules or bot processes changed by this task.
DELIVERY_STATUS_FULL_ACCEPTANCE: NO
DELIVERY_STATUS_EVIDENCE: cloud/delivery_status_001/preflight_evidence.json; cloud/delivery_status_001/CONTINUATION.json; state/receipts/DELIVERY-STATUS-PREFLIGHT-20260927-R4.json. R3 provider HTTP 500 classified and addressed by PR124; old failed evidence preserved. Details and deployment inputs in TASK_DELIVERY_STATUS_20260926.md.
