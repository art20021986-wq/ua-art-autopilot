# Independent review: code handoff v3

Date: 2026-09-09 UTC.

Verdict: **PASS for the bounded v2 → v3 storage-preflight correction.** No blocking defect introduced by this delta was found. This is neither production readiness nor an overall Gate B result.

## Exact reviewed inputs

| File | SHA-256 |
| --- | --- |
| `code_handoff_v3.py` | `200ca169be01cb12bf6cdaa8425acdb2279e1bfc6fd9306d51300148043f9ed1` |
| `test_code_handoff_v3.py` | `e24b11ae630b976c9cd794893172035ead72510dd8a8b530fc5b317963b208f7` |
| `server_fence.py` | `199a8744b3dd335899adcac92c52e30c462d7b471898d6b94a7ba944b9f05b85` |

The review compared the v3 installer and tests with their frozen v2 counterparts, read the surrounding install/rollback/terminal paths, and checked the storage requirement in `tasks/task_107.md`. The accepted application manifest remains complete17 v2, `12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136`.

## Findings

- The former shared-filesystem free percentage check is removed. `statvfs` now supplies an additional absolute free-byte check; it cannot substitute for account quota.
- Required capacity includes the actual old source bytes, the replacement payload, the largest staged replacement and 1 MiB of overhead. This is a conservative code-only estimate; it does not claim capacity for CRM, HTML or media backup.
- Account quota requires the exact five-field mapping, the authenticated-source label, integer used/quota bytes with a positive bounded quota, a hexadecimal receipt digest and a timestamp at most 30 seconds old. Missing, stale, future or malformed values do not authorize installation.
- Current account usage at 70% records a warning. Usage at 80% prevents the heavy deployment; at 90% it returns the emergency-stop reason. Insufficient remaining quota or insufficient shared free bytes also prevents deployment. These checks retain the TASK107 policy.
- The quota data comes from the existing independent `verify_window` boundary. Neither the source label nor a digest-shaped string authenticates it by itself. The implementation and v3 documentation explicitly state that a genuine authenticated upstream provider is still required; the test authority is synthetic.
- Storage checks occur before backup creation and target replacement. Failure preserves the six held locks and durable session intent, records `INSTALL_FAILED`, leaves target bytes unchanged and issues no success terminal receipt. No task resume, HALT change, CRM/HTML/media write or loaded-runtime claim is added.
- The schema bump does not weaken exact candidate/installer/session pinning, per-write authorization, conditional replacement, rollback or receipt readback.

## Verification

Copied the three exact inputs above to a new temporary directory under `/tmp`, then ran `python -B -m unittest -v test_code_handoff_v3` once. Result: **30 tests passed, zero failures/errors, exit code 0; 1.083 seconds**. All three source hashes were unchanged after the run.

The suite covers the shared-filesystem/account-quota distinction, absolute free-byte failure, 70/80/90 behavior, missing/stale quota, rollback after real fixture writes, interruption recovery, six-lock contention, replay, authority loss and no automatic unpause. Files, account quota and authority are synthetic; lock contention uses a real local child process. This review performed no platform API or production action. A PythonAnywhere receipt must be assessed separately.

## Remaining integration limits

A failed storage preflight intentionally consumes the durable installation session. With no `BACKUP_READY`, neither `read_terminal()` nor `rollback_only()` can manufacture a terminal success; a reviewed upstream recovery/new-session path is required. This follows the existing pre-backup failure policy and is safe but must remain visible to the caller.

Fresh authenticated quota capture, proven prior-writer drain, the exact owner-authorized plan, loaded-runtime verification and the overall production Gate B are still upstream obligations. Passing these tests must not clear `EXTERNAL_WRITER_VERIFICATION_REQUIRED`.
