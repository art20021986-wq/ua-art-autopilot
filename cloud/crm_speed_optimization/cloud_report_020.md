# CRM-SPEED-001 cloud report (task_023, continuation of task_020/022)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Scope actually executed

Claude authored a complete, self-consistent Gate A candidate package under `cloud/crm_speed_optimization/`. All Python files compile and are covered by an offline unit and integration test suite that runs against a fully synthetic fixture tree, never against the real `/home/Carix`. No production, CRM, database, bot, site, or media path was read or written by Claude while producing this package. PythonAnywhere Gate A was not executed by Claude; that requires the owner or ChatGPT-directed controller to run the no-argument launcher on the real server.

## Design decisions per specification section

- **Bounded inputs**: exactly the eleven required paths and two optional paths named in the specification are resolved, with symlink rejection and no recursive scanning.
- **A. Stop duplicate background runtimes**: `transform_usercustomize` removes top-level imports of CRM/bot/generator modules and top-level unconditional start/run/main/bootstrap calls; an already-inert file is left byte-identical. `transform_singleton_entry` requires an existing `if __name__ == '__main__':` anchor and injects an atomic O_CREAT|O_EXCL lock with PID/timestamp evidence and stale handling only inside that guarded entry point, never at import time.
- **B. Debounce and serialize rebuilds**: `transform_avtoperedacha` requires the three documented anchor functions (kolonki_cars, otpechatok, shag), replaces subprocess/os.system rebuild calls with a call into a bounded coalescing debounce queue (threading.Timer based, single pending flag, mutex protected), and never invokes the real generator itself.
- **C. Short SQLite ownership**: both `transform_avtoperedacha` and `transform_samokontrol` add an explicit short `timeout=` to `sqlite3.connect(...)` calls found via anchor detection, without touching schema, WAL, or PRAGMA mutation state.
- **D. Administrator CRM is text-only**: `transform_cars_ui` requires all four named admin functions and statically proves, via `find_reachable_media_calls`, that no reply_photo/reply_video/send_photo/send_video/media-group call remains reachable inside them after transformation, while leaving unrelated functions such as save_photo/delete_photo untouched.
- **E. Import safety**: none of the generated helper templates perform network, DB, process, or filesystem mutation at import time; they only define functions and idle state.

## Fail-closed behavior

Every transform function requires an explicit structural anchor (named function, import target, or `if __name__` block) before touching a candidate. If the anchor is missing or the file does not parse, that specific candidate is left unmodified and the run is reported BLOCKED with a specific reason, matching the requirement that missing or ambiguous anchors must never be guessed.

## Evidence produced by the engine at runtime

When actually executed against the real production paths (not done by Claude), the engine additionally performs a read-only, `PRAGMA query_only = ON` SQLite inspection bounded to 25 tables and 25 columns to record a non-PII match count for the UA-0009 keyword and to prove the database file is byte-identical before and after inspection, plus an optional no-redirect HTTP check of a UA-0009 URL if `CRM_SPEED_UA0009_URL` is explicitly configured (skipped, not fabricated, when not configured).

## Explicit limitations documented for the reviewer

- The AST-based subprocess-to-queue rewrite targets calls to `subprocess.run/Popen/call/check_call/check_output` and `os.system`; any other production-specific process-spawning idiom not matching this pattern will correctly leave the candidate unmodified and BLOCKED rather than being silently rewritten.
- The synthetic admin latency measurement (p95 target <= 2.0s) is a synthetic microbenchmark of the text-only reply helper only, and is explicitly not claimed as a production measurement.
- Static verification of DB-close-before-slow-work is limited to timeout injection plus anchor function presence; it does not attempt unsafe automatic reordering of arbitrary production code.

## Compliance statement

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
GATE_A_EXECUTED: NO
UA_0009_PUBLISHED: NO

Gate A was not run on PythonAnywhere by Claude. This package is READY_FOR_GATE_A_EXECUTION only, pending independent ChatGPT review and, separately, explicit owner approval for any Gate B production installation.
