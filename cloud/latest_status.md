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
DELIVERY_STATUS_STATUS: INSTALLED_PUBLIC_VERIFIED_BLOCKED_RECOVERY_AND_PENDING_ROUTER_FIX
DELIVERY_STATUS_CHECKPOINT: 2026-09-26T21:17:53.267Z
DELIVERY_STATUS_INSTALL_RUN: 36268504600 FAILURE; remote backup/install/verify PASS. Bot 266084 is Running and enabled. All 15 installed file hashes match plan; all 112 protected files and all CRM rows remain unchanged as observed at 2026-09-26T21:15:09Z.
DELIVERY_STATUS_PUBLIC: https://www.uaart.com.ua/video/katalog.html HTTP 200, body equals installed HTML; ordinary and cache-busted requests both match. Browser cache-busted counters: korea=4, ferry=4, georgia=6, kyiv=5, total=19.
DELIVERY_STATUS_FAILURE: Controller mistakenly checked /katalog.html, which redirects to /video/index.html. Automatic rollback reserved but not invoked: pinned recovery checkout omitted existing ledger-bound nonce, causing AUTOSTART_NONCE_RESERVATION_MISSING.
DELIVERY_STATUS_BLOCKER: state/AUTOPILOT_HALT.json active; transaction tx-36268504600-54c3be3cfc4dd0da remains ROLLING_BACK. No state marker was reset and no automatic rollback retry was attempted.
DELIVERY_STATUS_CORRECTIONS: Candidate routes all car_setstage callbacks through group -100 before legacy date side effects; controller checks the actual /video/katalog.html route and reports failures. These follow-up corrections are repository code only, not deployed.
DELIVERY_STATUS_TESTS: 55 local tests PASS, including legacy callback ordering and public redirect rejection.
DELIVERY_STATUS_SQL: Supplied and tested; not executed on live CRM. Two archived rows currently excluded by runtime projection.
DELIVERY_STATUS_NEXT: Read cloud/delivery_status_001/CONTINUATION.json and reconciliation_evidence_20260926.json. Resolve current transaction through registered manual recovery, correct and rehearse nonce copying in the rollback runtime, then create a fresh plan and install the router fix through main Actions. Do not replay the old installer, clear HALT without reconciliation, or repurpose TASK120-only recovery.
DELIVERY_STATUS_CONTINUATION: Existing automation 6ab80e71aa688191868f657b5631fcae remains enabled. It must inspect current recovery state before doing any installation.
DELIVERY_STATUS_FULL_ACCEPTANCE: NO

CRM_PERFORMANCE_TASK: UA-ART-CRM-PERFORMANCE-20260927
CRM_PERFORMANCE_STATUS: CANDIDATE_TESTED_NOT_INSTALLED
CRM_PERFORMANCE_OBSERVED: 2026-09-27 around 05:03-05:07 UTC. PythonAnywhere tarpit confirmed, CPU 8612.62 / 5000 seconds. Read-only cars GROUP BY 14.72 ms; not Telegram latency. Production source hashes match candidate inputs. Publication fence timeout and repeated catalog mismatches observed.
CRM_PERFORMANCE_CHANGE: Stage callback and periodic stage job notify the existing durable worker instead of competing for publication locks. Persisted catalog-error cooldown survives restarts and HTML timestamp changes; new CRM revision permits retry. Other transient failures retain per-card retries and do not starve other cars.
CRM_PERFORMANCE_PACKAGE: cloud/crm_performance_001/README.md and candidate_manifest.json
CRM_PERFORMANCE_TESTS: 15 PASS; actual full-source candidate compile PASS; unrelated CRM functions unchanged by AST comparison.
CRM_PERFORMANCE_PRODUCTION_WRITTEN: NO
CRM_PERFORMANCE_BLOCKER: Existing delivery EMERGENCY_HALT / ROLLING_BACK must be reconciled through the registered recovery route. CPU tarpit prevents meaningful speed acceptance and heavy rehearsal. No safety control was disabled; no new automatic installation was scheduled.
CRM_PERFORMANCE_NEXT: Reconcile delivery incident, resolve catalog-set mismatch, check CPU after reset, combine with current source/router corrections, complete exact backup/rollback/Gate B and main Actions installation, confirm loaded bot code and measure live opening/edit/save latency. Owner authorization already covers this repair; no duplicate general approval needed.
