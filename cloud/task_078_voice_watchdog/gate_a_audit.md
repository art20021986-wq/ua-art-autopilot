# Gate A — GET-only audit status

## Requirement (task_078)
Fetch fresh, secret-backed GET copies of:
- `cars_ui.py`
- `ai.py`
- `start_safe.py`
- `crm_online_guard.py`
- the actual launcher/supervisor manifest

and record SHA-256, definition hashes, handler order, current
timeout/worker/restart semantics, and confirm no existing kill path exists.
No live writes or restarts are allowed during Gate A.

## What this worker actually did
This Claude/Cloud worker operates without live secret-backed network access
to the PythonAnywhere/CRM environment. It cannot itself perform the
secret-backed GET calls required by Gate A. Therefore:

- **No live GET requests were issued by this worker.**
- The only confirmed fact available is the one supplied in the task
  directive itself: `cars_ui.py::catch_message` at
  `sha256=152d00158bcd097f61fad4e795340f45113724217b481d56ab32f358549a4fd5`
  uses a single `hard_deadline = started + 4.65` and runs `ai.transcribe`
  via `asyncio.to_thread(...)` under `wait_for`, and that cancelling
  `wait_for` does not stop the already-running thread.
- This single hash was **not independently re-verified** by this worker
  against a fresh GET in this round. It is treated as an unverified input
  fact pending independent controller confirmation, consistent with the
  canonical shared-memory rule that AI-reported facts are not accepted as
  verified until controller evidence exists (see REC-0011/REC-0013 pattern
  for task_015/task_021).

## What remains before Gate A can be marked complete
An operator or controller with live, secret-backed GET credentials must:
1. Fetch the four files above plus the launcher/supervisor manifest.
2. Record SHA-256 of each file exactly as retrieved (no edits).
3. Confirm handler registration order for message types (voice/audio/text/
   photo) is unchanged from what the patch below assumes.
4. Confirm whether an OS-level supervisor (systemd/PA "always-on task"/
   process manager) already restarts the Telegram process on non-zero exit,
   and record its restart-count/window/backoff behavior.
5. Confirm there is currently **no** existing kill/TERM/KILL path for the
   `asyncio.to_thread` STT call (task_078 states there is none; this must
   be independently confirmed, not assumed).

Until (1)-(5) are recorded as controller-verified evidence in canonical
memory, this package remains `READY_FOR_CONTROLLER_GATE_A_EXECUTION`, not
`PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.

## Design assumption used for the sandbox/patch below
Because live source cannot be fetched by this worker, `handler_patch.py`
is written as a **contract-compliant reference implementation** to be
diffed against the real `catch_message` by whoever runs Gate A, rather than
an in-place patch blindly applied to an unseen file. The installer
(`installer.py`) requires the operator to supply the actual fetched file and
its SHA-256 before it will apply anything, and it always keeps a timestamped
backup plus a rollback function.
