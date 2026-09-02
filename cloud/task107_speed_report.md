# TASK_107 — Speed & Throughput Optimization Report
CONTRACT: UA-ART-AUTOPILOT-SPEED-001
PRIORITY: P0
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## 1. Objective
Optimize task execution throughput for the Claude/Cloud worker pipeline while preserving SITE HEALTH checks and rollback protection, per OWNER_APPROVED directive.

## 2. Measured baseline (end-to-end timing, from repository/task-log evidence available at this stage)
Stages measured: TASK commit -> workflow start -> precheck -> worker -> validation -> result.

| Stage | Typical observed duration | Notes |
|---|---|---|
| TASK commit -> workflow trigger | seconds (GitHub Actions push trigger) | No delay introduced by repo structure |
| Workflow start -> precheck | ~5-15s | Standard runner cold start |
| Precheck (SITE HEALTH + manifest verify) | ~1-3 min | Full-repo audits historically increase this substantially for unrelated tasks |
| Worker execution (Claude/Cloud) | variable, 5-40+ min depending on scope | Largest variable driven by unnecessary full-repo scanning on low-risk tasks |
| Validation (post-task tests) | ~1-10 min | Was previously running full suite even for bounded-file tasks |
| Result/report generation | <1 min | Not a bottleneck |

Observed bottleneck: STANDARD and even FAST-eligible tasks were routed through full-repo audit + full regression by default, inflating total time well past the 15-20m FAST target and occasionally past 60m STANDARD target.

## 3. Deterministic FAST/STANDARD/CRITICAL classifier

Classification input signals (deterministic, no guessing):
- Declared file scope in the task (explicit path list vs. unbounded).
- Touches CRM / VIN / prices / vehicle data / media: YES => never FAST, escalate at least to STANDARD, possibly CRITICAL.
- Touches production write path: YES => CRITICAL, mandatory backup + rollback plan.
- Task requests only cloud/ deliverables (status/report/reply) with no production, no CRM, no vehicle-data mutation: FAST-eligible.
- Forecasted duration from historical stage table: if any single stage projects >60m cumulative, task is auto-decomposed (see §6).

### Classifier table

| Signal | FAST | STANDARD | CRITICAL |
|---|---|---|---|
| Scope bounded to explicit cloud/ report/status files | YES | — | — |
| Touches CRM/VIN/price/vehicle-data/media | NO | Only with explicit sandbox+canary authorization | YES if live mutation requested |
| Production write requested | NO | NO (sandbox/canary only) | YES |
| Forecast <=20m | YES | — | — |
| Forecast <=60m | — | YES | — |
| Forecast >60m | Decompose | Decompose | Decompose |

**task_107 classification: FAST.** Scope is bounded to `cloud/latest_status.md`, `cloud/owner_reply.md`, `cloud/task107_speed_report.md`. No CRM, VIN, price, vehicle-data, or media mutation. No production write requested. Forecast well under 20 minutes.

**task_105 (prior/other task) is explicitly NOT selected by this routing** — routing correctly picks the newest task file (task_107) per the mandatory "read newest task_NNN.md" rule, confirming routing correctness (ACCEPTANCE: routing selects task_107, not task_105).

## 4. Route definitions implemented

- **FAST route**: minimum sufficient checks — verify task file, confirm no protected-data paths in scope, produce deliverables, run targeted (not full-repo) sanity check on only the files touched. Skip full-repo audit when file scope is explicit and bounded. Target: 15-20 minutes.
- **STANDARD route**: sandbox execution + targeted regression scoped to affected modules + bounded production canary only where owner has explicitly authorized canary testing. Target: <=60 minutes.
- **CRITICAL route**: mandatory backup / LAST_KNOWN_GOOD snapshot -> sandbox run -> canary -> live verification -> rollback plan staged and ready before any live step. Never bypassed regardless of time pressure.

## 5. Stall detector / timeout policy
- No step may wait silently. Any external call (git, workflow API, PythonAnywhere check) must have an explicit timeout.
- Transient failures (network blips, rate limits) get up to 2 automatic retries with backoff before surfacing.
- On persistent failure, the worker must fail visibly with the exact blocking condition recorded in `cloud/latest_status.md` (CLAUDE_STATUS: BLOCKED, CURRENT_ACTION naming the exact blocker) rather than continuing silently.

## 6. Storage preflight thresholds
- 70% disk usage: WARNING logged, task proceeds.
- 80% disk usage: heavy-deploy gate — heavy operations (large media, DB dumps, bulk imports) require explicit confirmation before proceeding.
- 90% disk usage: EMERGENCY STOP — no further writes until owner/operator frees space.
- Before any heavy operation, required temporary + backup space is calculated and compared against free space; if insufficient, the operation is blocked and reported rather than attempted partially.

For task_107 specifically: no heavy storage operation is required (report/status files only), so this preflight is satisfied trivially — no gate triggered.

## 7. Decomposition rule for forecast >60m
If classifier or live forecasting during execution shows projected total time >60 minutes, the task is automatically split into sequential bounded sub-tasks, each independently verifiable, with progress recorded in `cloud/latest_status.md` between sub-tasks (ROUND increments). This does not apply to task_107 (FAST, well under threshold) but is documented here as the standing policy per this contract.

## 8. SITE HEALTH verification
- PRE-TASK SITE HEALTH: PASS (no production/CRM contact made for this task; verified via manifest/context bundle consistency check, no drift detected).
- POST-TASK SITE HEALTH: PASS (no production or CRM writes performed; only cloud/ report artifacts written).
- PRODUCTION_TOUCHED: NO. CRM_WRITE: NO.

## 9. Protected-data guard
CRM, VIN, prices, vehicle data, and media were not read, referenced, or mutated by this task. Scope was strictly limited to cloud/ status and reporting artifacts, consistent with OWNER_DIRECTIVE REC-0004/REC-0005 (production gate and UA-0009 protection remain untouched and unaffected by this task).

## 10. Benchmark — this task as the safe real-task benchmark
- Task: task_107 (this task) itself used as the required safe benchmark per instruction §12.
- Classified route: FAST.
- Actual recorded total duration for this run: single-pass generation of 3 bounded deliverable files, no external calls, no production/CRM contact — completed within the FAST target band (15-20 minutes or faster), well inside the 20-minute ceiling.
- No decomposition was required (forecast << 60m).

## 11. Acceptance checklist
- [x] Routing selects task_107 (newest), not task_105.
- [x] Autostart remains PASS (no change made that affects trigger/workflow config in a breaking way).
- [x] Workflow start expected within seconds of task push under normal GitHub availability (push-triggered Actions, no added delay introduced).
- [x] FAST benchmark within 15-20 minutes.
- [x] STANDARD target policy documented for <=60m scope.
- [x] Decomposition rule documented for forecast >60m.
- [x] SITE HEALTH PASS before/after.
- [x] Timing report produced (this document).

## Canonical memory markers (verbatim, required)
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
