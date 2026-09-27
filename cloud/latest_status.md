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

STAGE_EDIT_RECOVERY_TASK: UA-ART-STAGE-EDIT-RECOVERY-001
STAGE_EDIT_RECOVERY_CHECKPOINT: 2026-09-27T05:07:18Z
STAGE_EDIT_RECOVERY_STATUS: CANDIDATE_TESTED_BLOCKED_RECOVERY_AND_CPU
STAGE_EDIT_RECOVERY_LIVE: Read-only observation: UA-0021 is published=1, status=sea_loaded in CRM but absent from server catalog. CRM has 20 active rows; server catalog has 19. These supersede yesterday's fixed acceptance count; use fresh CRM inventory for verification.
STAGE_EDIT_RECOVERY_CAUSE: publikaciya._ua9_sobrat_katalog returns archived rows although renderer and transaction validator use active rows, causing CATALOG_ROW_SET_MISMATCH and rollback (UA-0021 log 2026-09-27 04:51:50 UTC). Stage-only patch also rejects missing reactivated cars with CATALOG_PUBLISHED_SET_MISMATCH.
STAGE_EDIT_RECOVERY_FIX: Source-pinned two-file candidate uses one active publication inventory, routes stage changes through the existing durable publisher and accepts old valid active-stage callbacks before legacy handlers. Drafts remain unpublished; removed/unknown status policy remains hidden.
STAGE_EDIT_RECOVERY_TESTS: 18 regression tests and 7 existing policy tests PASS. Exact installed source reconstruction and candidate compile PASS. Full live rehearsal and public acceptance NOT_RUN.
STAGE_EDIT_RECOVERY_BLOCKERS: Existing EMERGENCY_HALT / ROLLING_BACK transaction requires registered recovery and nonce-complete rollback rehearsal. CPU approximately 8576.84/5000 seconds at 04:54 UTC; next reset 08:37:11 UTC. Quota reset alone is insufficient.
STAGE_EDIT_RECOVERY_PRODUCTION_TOUCHED: NO live source, HTML, CRM records or bot restart by this task.
STAGE_EDIT_RECOVERY_NEXT: cloud/stage_edit_recovery_001/README.md and CHECKPOINT.json. After registered recovery, use a fresh bounded two-file plan through main Actions. Do not replay the original installer, reset sync state or clear HALT without reconciliation. Coordinate overlapping source changes with the pending CRM/media repair.
STAGE_EDIT_RECOVERY_FULL_ACCEPTANCE: NO

CRM_PERFORMANCE_TASK: UA-ART-CRM-PERFORMANCE-20260927
CRM_PERFORMANCE_STATUS: CANDIDATE_TESTED_NOT_INSTALLED
CRM_PERFORMANCE_OBSERVED: 2026-09-27 around 05:03-05:07 UTC. PythonAnywhere tarpit confirmed, CPU 8612.62 / 5000 seconds. Read-only cars GROUP BY 14.72 ms; not Telegram latency. Production source hashes match candidate inputs. Publication fence timeout and repeated catalog mismatches observed.
CRM_PERFORMANCE_CHANGE: Stage callback and periodic stage job notify the existing durable worker instead of competing for publication locks. Persisted catalog-error cooldown survives restarts and HTML timestamp changes; new CRM revision permits retry. Other transient failures retain per-card retries and do not starve other cars.
CRM_PERFORMANCE_PACKAGE: cloud/crm_performance_001/README.md and candidate_manifest.json. Combined builder reuses stage_edit_recovery_001 and outputs three files (cars_ui.py, publikaciya.py, ua_crm_public_sync.py); do not install separate overlapping candidates.
CRM_PERFORMANCE_TESTS: 40 PASS (15 performance, 18 stage recovery, 7 status policy); full-source combined candidate compile PASS; existing stage candidate outputs preserved byte-for-byte.
CRM_PERFORMANCE_PRODUCTION_WRITTEN: NO
CRM_PERFORMANCE_BLOCKER: Existing delivery EMERGENCY_HALT / ROLLING_BACK must be reconciled through the registered recovery route. CPU tarpit prevents meaningful speed acceptance and heavy rehearsal. No safety control was disabled; no new automatic installation was scheduled.
CRM_PERFORMANCE_NEXT: Reconcile delivery incident, resolve catalog-set mismatch, check CPU after reset, combine with current source/router corrections, complete exact backup/rollback/Gate B and main Actions installation, confirm loaded bot code and measure live opening/edit/save latency. Owner authorization already covers this repair; no duplicate general approval needed.

CRM_INSTALL_CONTINUATION_TASK: CRM-RELEASE-RECOVERY-20260927
CRM_INSTALL_OWNER_COMMAND: «Устанавливай на рабочую CRM немедленно.» Installation is already authorized; no repeated general permission requested.
CRM_INSTALL_STATUS: NOT_INSTALLED_BLOCKED_BY_PENDING_TRANSACTION
CRM_INSTALL_OBSERVED: 2026-09-27 around 05:32 UTC; PythonAnywhere bot 266084 and monitor 270984 Running; CPU 8716.57 / 5000 seconds, tarpit active. Expected quota reset 08:37:11 UTC / 15:37:11 Asia/Ho_Chi_Minh; not a deployment appointment or proof of readiness.
CRM_INSTALL_GATES: Unchanged pinned verify-mode rejects AUTOMATIC_MODE_HALTED. Unchanged watchdog discover validates exactly one pending transaction, tx-36268504600-54c3be3cfc4dd0da, ROLLING_BACK. Existing TASK120-only recovery cannot close this incident.
CRM_INSTALL_RECOVERY_PREPARATION: cloud/crm_release_recovery_20260927/README.md. Inert nonce-workspace.patch adds the missing ledger-bound nonce to both existing rollback worktree copy steps. It is not applied to active workflows and is not a runtime activation.
CRM_INSTALL_RECOVERY_TESTS: 10 tests PASS executing both actual embedded copy blocks. Two incident rehearsals using source commit 9fd580ca61c67dfb944bc4826fd1f18459ffba0b and unchanged pinned validators reproduce AUTOSTART_NONCE_RESERVATION_MISSING before the candidate and pass ledger verification after it. ROLLING_BACK remains unchanged. Evidence: cloud/crm_release_recovery_20260927/rehearsal.json.
CRM_INSTALL_PUBLIC_MONITOR: main run 36296990449 SUCCESS at 05:22 UTC, both canonical pages HTTP 200. This does not establish CRM speed or complete catalog correctness.
CRM_INSTALL_PRODUCTION_WRITTEN: NO. No bot restart, active workflow/runtime/approval/nonce/claim/transaction/HALT modification, rollback invocation or launch marker created.
CRM_INSTALL_NEXT: Register and verify the nonce-complete runtime update and evidence-bound manual recovery for the delivery incident, preserving subsequent CRM edits. After recovery use the combined three-file PR130 builder, fresh backup/rollback/Gate B and main Actions. Never replay the original install or mark an unexecuted rollback successful. Read this checkpoint before the existing 15:40 Vietnam continuation; its schedule/prompt were not changed.

CRM_ONECLICK_TASK: UA-ART-CRM-ONECLICK-PUBLISH-001
CRM_ONECLICK_STATUS: CANDIDATE_TESTED_NOT_INSTALLED; GATE_B_NOT_READY
CRM_ONECLICK_SCOPE: Remove already-in-catalog/hide ad section and buyer preview; publish from one tap for drafts and stale published flags; no toggle on repeated publish; durable retry and verified completion receipt.
CRM_ONECLICK_CAUSE: ad_screen bypassed publication when published=1; archive-inclusive catalog inventory caused strict transaction rollback. The publication flag is intent, not proof of a public page.
CRM_ONECLICK_PACKAGE: cloud/crm_oneclick_publish_001/README.md and candidate_manifest.json; tasks/UA-ART-CRM-ONECLICK-PUBLISH-001.md. Builder composes current stage and performance candidates; preserves their fixes.
CRM_ONECLICK_TESTS: 68 local tests PASS (28 oneclick, 15 performance, 18 stage recovery, 7 status); exact-source four-file candidate compiles. Production rehearsal/browser acceptance NOT_RUN.
CRM_ONECLICK_BLOCKED: Delivery transaction tx-36268504600-54c3be3cfc4dd0da remains ROLLING_BACK / EMERGENCY_HALT. Fresh dashboard CPU 8716.57/5000, tarpit. Existing resource and recovery gates preserved.
CRM_ONECLICK_PRODUCTION_WRITTEN: NO; no runtime source, HTML, CRM rows or bot restart by this task; UA-0021 publication not confirmed. No new delayed deployment scheduled.
CRM_ONECLICK_NEXT: Registered delivery recovery, fresh CPU/source checks, combine PR128 media changes, exact backup/install/rollback including private request ledger, Gate B and main Actions release, verify one-click publication and completion in Telegram and public site. Owner authorization already covers this repair.
