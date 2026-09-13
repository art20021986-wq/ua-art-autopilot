# PythonAnywhere task configuration controller

Prepared 9 September 2026. No live task was paused, resumed, created, deleted or
reconfigured by these tests. All controller mutations use an isolated fake API.

`platform_control.py` supplies an explicit library API, with no CLI or import-time
network action. The fixed account is Carix on www.pythonanywhere.com. Only list
GETs and enabled-only PATCHs for the four reviewed task IDs are possible. The
official API documents these endpoints and the `API_TOKEN` environment variable:
[PythonAnywhere API](https://help.pythonanywhere.com/pages/API/).

## Reviewed scope

| Resource | ID | Temporary action |
| --- | --- | --- |
| CRM always-on task | 266084 | Disable, then restore its original enabled flag |
| SEO daily task | 1502215 | Disable, then restore its original enabled flag |
| TASK083 daily installer | 1502679 | Disable, then restore its original enabled flag |
| TASK096 daily task | 1505035 | Disable, then restore its original enabled flag |

Every inventory must contain precisely these identities with their reviewed
commands, descriptions, expiry and scheduling configuration. Unknown or missing
tasks, duplicate IDs and changed settings stop the controller. Extra provider
fields are retained in the plan and compared on readback. Runtime `state` is
explicitly excluded from configuration equality: an enabled flag is not proof
that an existing process has stopped.

## Integration contract

1. `build_plan(inventory, main_sha, run_id, nonce, epoch, owner_review)` binds an
   exact main SHA, nonzero run ID, 64-character hexadecimal nonce, monotonic
   epoch and owner review reference to the entire inventory. It produces a
   SHA-256 digest. The reference alone grants no execution permission.
2. Construct `Controller(api, journal_dir, verify_plan=...)`. The verifier must
   independently validate current main/run/nonce/epoch and actual authorization,
   returning `AUTHORIZED` with all binding fields. The callback runs again before
   every PATCH. A constant or caller-supplied boolean is not a verifier.
3. `pause(plan)` journals an intent durably before each enabled-only PATCH and
   reads the full inventory before and after. Its result is only
   `PAUSED_CONFIGURATION_VERIFIED`, with `external_writer_proof: false`.
4. The orchestrator must obtain a separate current server fence, including
   already-running scheduled children and every other writer, before backup or
   application mutation. This module neither removes HALT nor implements that
   proof. It does not change the existing production authorization requirements.
5. `restore(plan, receipt, verify_terminal=...)` requires an independently
   verified commit, rollback, or no-data-write terminal receipt bound to this
   plan/run/nonce/epoch. It restores schedules first and CRM last. It never enables
   a task whose original enabled flag was false, and never overwrites changed
   commands, descriptions or schedule settings. A changed terminal receipt is
   refused after restoration begins.
6. A successful restore returns `TASK_CONFIGURATION_RESTORED`, with
   `runtime_health_verified: false`. Actual worker health, loaded code, queue,
   site readback and source checks remain separate mandatory checks.

## Persistent coordination and uncertainty

Real `PATransport` requires exactly
`/home/Carix/autopilot_state/writer_coordination_001`. This is a persistent
PythonAnywhere path, not an equivalent path on an ephemeral GitHub runner.
There is no alternate-directory or ephemeral-state fallback. Provisioning its
parent and selecting a reviewed execution process are explicit integration work.
One journal directory owns one plan. Its account-wide lock and journal must be
regular single-link files, owned by the current UID, with no group/world access;
symlink parents, replaced resources, FIFO files and torn journals are refused.

The same journal supports repeated calls after a known successful step without
duplicate PATCHs. A timeout or uncertain PATCH keeps its durable intent pending.
`reconcile(plan)` only observes the current configuration. Even the target value
returns `INTENT_EFFECT_OBSERVED_UNSETTLED` and leaves execution blocked: readback
cannot prove that a delayed old request will never be applied later. Optional
`verify_completion` must supply independently verified remote completion evidence
for the exact intent; no such PythonAnywhere completion provider is implemented
here. The controller never blindly retries an ambiguous write or resumes tasks
on a timer.

HTTP redirects are refused; requests use fixed host/paths, a 20-second timeout,
bounded response reads and at most 30 requests/minute per transport instance.
There are no automatic HTTP retries. Secrets and response bodies are omitted
from errors and journals. The account-wide journal lock must be used for all
mutating calls; directly invoking the low-level transport is not an execution
route and does not provide controller guarantees.

## Verification scope

36 isolated local tests cover pause/restore, unchanged configuration, disabled
tasks, authorization bindings, duplicate/missing tasks, timeout uncertainty,
partial failure, changed settings, terminal receipts, concurrent controllers,
durable intent ordering, hardlinks, FIFOs, lock replacement, malformed/torn
journals, endpoint limits, redirect refusal, bounded reads and error redaction.
They do not claim live API permission, production quiescence, Gate B PASS or
successful production deployment.
