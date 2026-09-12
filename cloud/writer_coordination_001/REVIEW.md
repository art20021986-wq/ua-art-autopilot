# Independent writer-coordination review

Date: 2026-09-09. Scope: preparation and isolated local tests only. No PythonAnywhere processes, settings, production files, CRM records, HALT or queue state were changed by this review.

## Reviewed fence component

`server_fence.py` SHA-256: `199a8744b3dd335899adcac92c52e30c462d7b471898d6b94a7ba944b9f05b85`.

Result: **PASS for `LEGACY_LOCKS_HELD_ONLY` scope**. This is not a full external-writer verification, a deployment approval, a cross-host PythonAnywhere lock proof, or a Gate B result.

The reviewer independently ran the 19-test suite, including actual competing local processes, holder death, partial acquisition, missing/replaced locks, stale intent, wrong context, challenge replay and injected disk-full/unlock errors. All 19 passed. These are the same tests reported by the author and must not be added as 19 extra unique checks.

Two defects were independently reproduced in the initial implementation and corrected before this result:

1. Challenge sequence A → B → A could renew A's validity. The corrected holder retains all used challenges for its instance and rejects A's replay.
2. Failure to write the intent journal during cleanup could leave owned locks held in a live process. Cleanup now attempts to release/close every owned descriptor even when journaling or one unlock fails.

Separate reviewer repros on the reviewed hash confirmed `challenge_A_B_A=REJECTED` and `close_write_failure=LOCK_AVAILABLE` after an injected `OSError(28)`.

The helper preserves the durable intent, refuses missing or replaced resource lock inodes, and declares `external_writers_verified=false` and `cross_host_lock_verified=false`. Its fixed CLI roots must be enforced by a reviewed launch path. The injectable roots used by unit tests are not production provenance: a receipt schema and source hash alone do not prove that the holder used `/home/Carix`.

## Reviewed platform configuration component

`platform_control.py` SHA-256: `82489cd9dd20331ea90b668138c12f5c594a1e40df186f7170fd7b783ce612d9`.

Result: **PASS for isolated task-configuration coordination preparation**. The reviewer independently ran all 36 tests in `tests/test_platform_control.py`; all passed. They use fake API responses and do not prove live API permission, actual task pause, process termination or runtime health. These 36 are the author's same test cases, not 36 additional unique checks.

The initial controller accepted an empty journal hardlinked to an unrelated file. An independent repro obtained `PAUSED_CONFIGURATION_VERIFIED`, four fake API mutations and 1,331 bytes written to the unrelated file. The reviewed implementation rejects the same setup with `JOURNAL_RESOURCE_CHANGED_OR_UNSAFE`, zero remote mutations and zero unrelated bytes written. It also rejects special files without blocking, symlink parents, replaced lock inodes and invalid journal transitions before subsequent mutation.

Controller context now matches the fence's limits: nonzero run ID of at most 20 digits, a 64-character hexadecimal nonce and a positive signed-64-bit epoch. A real `PATransport` must use one fixed coordination directory; separate per-session locks are not a substitute for an account-wide coordinator.

Timed-out PATCH requests retain durable uncertainty. Merely reading the desired enabled value returns `INTENT_EFFECT_OBSERVED_UNSETTLED` and does not permit automatic continuation or restore. An independent verified completion receipt is required to settle that operation; the module does not pretend PythonAnywhere supplies a request operation ID. Authoritative completion, plan authorization and terminal-result verification remain integration responsibilities, not supplied by unit-test callback mappings.

`JOURNAL_ROOT` is `/home/Carix/autopilot_state/writer_coordination_001`. Its durability assumes execution on the reviewed persistent server filesystem. Creating a directory with that name on an ephemeral GitHub runner would not preserve the journal across jobs. Production integration must establish the actual execution host and durable bootstrap; no path fallback is approved by this review.

## Reviewed analytics HTML writer patch

`patch_analytics_writer.py` SHA-256: `58e62afbc8458f273b605b06b222552ff07d83d9fd375c5891685045a070e2e5`.
Source-backed tests SHA-256: `64892d7695c8a675510eb5c80db13a2e0b3ccbdadc9d818d38b0922847f88981`.

Result: **PASS for exact-source patch preparation and 13 isolated tests**. The captured source hash is `a73be46099596322dcd607ecadd56140d45483a5ad38f1c1a0a0e395cfc8bc94`; the resulting patched WSGI bytes hash is `cb6fc54ae832eb768eb70f2815e010db46e15614ef1864acc3dd0d843386fc23`. No WSGI deployment or reload was performed by this review.

The actual `_storozh` function reads a complete HTML file, inserts the existing analytics marker, then replaces the file. Without coordination, a concurrent publisher can write a newer specification between that read and replace, after which the old body overwrites it. This proves a concrete lost-update mechanism, not that this race caused the historical incident.

The patch retains the original function body and unrelated module AST. It holds the existing publication lock around the complete read/transform/replace cycle, defers without waiting when busy, never recreates a missing lock, rejects unsafe or replaced inodes, rechecks the existing stop condition, and defers whenever a durable coordination intent exists.

The reviewer found and independently reproduced a defect in the initial intent check: `os.path.lexists` suppresses lookup errors, so an injected EACCES let HTML change and advanced the two-minute timer. The corrected code uses explicit `lstat`; only a missing path is treated as absence, while other errors defer. An independent rerun confirmed no HTML change and no timer advance. The lock open now uses `O_NONBLOCK` before type validation, preventing a special-file open from stalling an HTTP request. All 13 source-backed tests passed independently; they are the same author's cases, not 13 additional unique checks.

## Reviewed TASK083 admission patch

`patch_task083_writer.py` SHA-256: `6857483c3ee21fddb326278fe3ab3aa8eee85ebb82de9ff4048d59db14d870d2`.
Tests SHA-256: `932229ed4a69d19f4314bd0a494812b48311762fd78a531291d86a1f9b25f761`.

Result: **PASS for exact-source admission patch preparation and 11 local source-backed tests**. Source hash is `13dbcbced164c73bb1767fee6d35ca9597c14b552baaeb31ebbf90cad70b1b46`; resulting installer hash is `13b61a13b73f4a029b01fa0f3c071ab8d4790b656d8fa5f37876e92ac5231684`.

The common publication lock is acquired before main's existing three locks, whose order remains repair → runtime guard → dedup. Direct `run_install` and `run_rollback` calls also enter common admission. Same-thread nesting is reentrant and checks PID ownership; inherited admission is rejected. A persistent intent or intent lookup failure defers the operation, unsafe/missing locks are not recreated, and original payload `OSError` values remain observable. Only admission helpers/decorators and removal of the exact legacy lock-touch loop change the original AST.

The tests execute the actual selected source functions with synthetic roots and bounded fake payload dependencies. They are not a full production installer run, a cross-host lock proof or a verification that an existing worker has loaded the patch. The same 11 tests were independently rerun successfully, without claiming extra unique cases.

An early admission rejection occurs before the old main body and intentionally leaves any prior install receipt unchanged. A caller must therefore require the current process exit and a current operation-bound receipt. A stale `PASS` file must never be accepted as success of the deferred run. Already-running unpatched installers still require separate drain before deployment.

## Reviewed coordination server-test launcher

`coordination_server_gate.py` SHA-256: `7f27b63b5b5e0f2a3aa01fe3c78524288e1069cb89c675b9f164cf62ce92bcab`.

Approved for the fixed isolated PythonAnywhere test stage and exact frozen bundle only. The launcher verifies the bundle, creates a new run directory, starts a child with a minimal environment, and runs the existing 19 fence plus 36 configuration tests. Application imports and real task API operations are outside its scope. The child installs Python audit guards for network, subprocess and filesystem effects; this is a reviewed trusted-code test harness, not an OS sandbox for hostile native code. Approval of the launcher is not evidence that its server run passed.

`analytics_server_gate.py` SHA-256: `9999f43434dbc65c0fe69c773c26668d6a3c323b698abf6df5252278c07d088c`.

The analytics launcher delta is also approved for its fixed isolated test stage. Its parent reads exactly the pinned `/home/Carix/analitika_wsgi.py` without following links, checks source hash and inode/mtime stability, and copies it into the new run's private inputs. The child can read that staged copy and execute the 13 source-backed function tests against synthetic pages. It does not import or reload the live WSGI application. Parent readback verifies the production source remains unchanged. The previously reviewed child audit guards are unchanged.

## Invariants required before production integration

- Durable pause must include proof that every prior scheduled invocation terminated. Holding all TASK083 locks excludes a current writer but does not exclude an already-started installer waiting for those locks. On holder death that waiter can resume despite the disabled schedule. The test suite demonstrates this limitation.
- Source inventory must cover startup mutations, direct SQLite connections, diagnostic/web/manual writers and subprocesses. An empty `/proc` view in a separate PythonAnywhere console is not an account-wide process proof.
- Preserve TASK083's lock order: repair, runtime guard, dedup. Also account for startup singleton, publication and CRM DB locks. Never unlink resource locks to break a conflict.
- Platform pause/restore must retain exact task IDs and original settings. Journal before mutation, read back each change, preserve partial-failure state, and refuse to overwrite configuration changed by another actor.
- A live receipt must be freshly obtained through the fixed authenticated transport and bound to current main, plan hash, workflow run/attempt, nonce, epoch, reviewed holder command/source and paused/drained inventory. Recheck with a new challenge immediately before the final compare-and-swap.
- Receipt expiry or holder death must not automatically clear the durable intent or resume writers. A fresh receipt still cannot close the crash-to-CAS race unless durable pause and actual prior-process drain are independently established.
- The keeper holds locks used by the real publisher and CRM connection. A separate publisher process will block on them. Actual publication needs a reviewed handoff or execution contract; starting an ordinary writer while the keeper holds those locks is not such a contract.
- Read back the final commit and server state after the operation. Preserve backup/rollback and the original operation identity instead of starting another TASK120.

## Registered recovery route

The current route's `_rcanary` binds its immutable v1 receipt to all current runtime hashes. Changing the watchdog, workflow or runtime manifest therefore requires a newly verified canary identity/path for the new pinned runtime. Do not modify the old canary, fabricate its pins, or reuse its result as validation of changed code.

Keep `recovery_proposal` pure. A bounded transport capture should obtain live proof; validation should bind its digest, nonce and epoch to the proposal and execution receipt. `recovery_verify` must check the same binding. Checking only a local JSON flag or replacing the unconditional exception with `True` is insufficient.

Preserve the owner's exact-plan command, current main compare-and-swap, global writer group, queue, claims, terminal transaction, consumed nonce history and HALT archive. This review approves the scoped helper preparation only. It does not remove `EXTERNAL_WRITER_VERIFICATION_REQUIRED` from the working route.
