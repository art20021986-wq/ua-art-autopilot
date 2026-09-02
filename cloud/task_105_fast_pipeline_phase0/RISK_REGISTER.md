# RISK_REGISTER.md — TASK 105 Phase 0

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Workflow inventory is provisional; real `.github/workflows/` listing not confirmed in this session (BLOCKER-INV-01) | High (known) | Medium — could misclassify a workflow's production-write capability | Do not act on classification until Stage 1 of MIGRATION_PLAN.md confirms live listing; no deletions/disables performed in Phase 0 |
| R2 | TASK096 v3–v8 root cause is inferred from narrative, not byte-level diff (BLOCKER-RC-01) | Medium | Medium — proposed preflight fixes might miss an undocumented failure mode | Request actual diffs/logs before Phase 1 implementation of preflight checks |
| R3 | Resource-aware locking could introduce race conditions if two lock keys unexpectedly map to the same underlying resource | Medium | High (could double-write production) | Stage 4 requires sandbox-only testing behind a default-off feature flag before any production use |
| R4 | New canonical state machine could be misread by legacy consumers expecting old `CLAUDE_STATUS` semantics only | Medium | Medium | Stage 5 mandates additive-only schema changes, no redefinition of existing fields |
| R5 | AI routing budget rules (NO_AI/GPT_PRIMARY/etc.) could be gamed by misclassifying CRITICAL tasks as FAST to save cost | Low-Medium | High (bypasses DUAL_REVIEW safety) | Classification rule must be deterministic and keyword/path based (e.g., any touch of production/CRM/PythonAnywhere/Cloudflare/DNS paths forces at least STANDARD, never FAST) — encode this explicitly in Phase 1 orchestrator design |
| R6 | Global production queue serialization removal is a safety-relevant production change | Low in Phase 0 (not implemented) | Critical if implemented incorrectly | Explicit owner approval required before Stage 4 is enabled outside sandbox; this task performs no such change |
| R7 | Owner approval ambiguity (FINISHED vs AWAITING_PRODUCTION_APPROVAL) already causing possible false-finished reports today | Medium (per task096 history) | Medium-High | CURRENT_STATE_MACHINE.md + TARGET_ARCHITECTURE.md propose the fix; adoption gated in Stage 5 |
| R8 | This Phase 0 report itself could be mistaken for a deployment | Low if reply is clear | Medium (owner confusion) | owner_reply.md explicitly states this is audit-only, no production/CRM/PythonAnywhere/Cloudflare/DNS change |

## Outstanding blockers carried into Phase 1 prerequisites
- BLOCKER-INV-01 (live workflow listing)
- BLOCKER-DEP-01 (live YAML concurrency/needs graph)
- BLOCKER-RC-01 (TASK096 v3–v8 verified diffs)

None of these blockers required stopping Phase 0, since Phase 0's deliverable is explicitly an audit/plan, not an implementation; they do gate the start of Phase 1 implementation quality.
