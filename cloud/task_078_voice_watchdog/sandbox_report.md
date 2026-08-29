# Sandbox report — TASK 078

## Status of execution
This worker authored the full watchdog package and an offline pytest suite
(`tests/test_watchdog.py`) covering every scenario listed in task_078's
"Sandbox tests" section:

- duration 0/3/30/60/120/600 and boundaries 15/180 — `test_compute_stt_timeout_bounds`
- short voice PASS with one attempt — `test_short_voice_pass_first_attempt`,
  `test_short_voice_end_to_end_single_success_single_write`
- first attempt hangs → killed → fresh worker path — worker-level hang test
  covers the kill mechanics (`test_first_attempt_hangs_worker_killed_no_second_success`);
  handler-level dual-hang failure is covered by
  `test_two_hangs_produce_one_failure_zero_writes_retryable_marker`
- two hangs → one failure, zero writes, retryable marker — same test above
- exception/cancellation path → process killed/reported, no parent crash —
  `test_exception_in_child_is_reported_not_crashing_parent`
- 20 parallel calls, bounded concurrency, no shared-state corruption —
  `test_twenty_parallel_short_voice_calls_all_succeed_independently`
- duplicate Telegram update → one transcription/one CAS write —
  `test_duplicate_telegram_update_single_transcription_single_write`
- restart/replay after simulated process restart → no duplicate write —
  `test_restart_budget_replay_after_simulated_process_restart`
- circuit breaker opens after 3 hangs/10min, cooldown, stays closed for
  text — `test_circuit_breaker_opens_after_three_hangs_within_window`,
  `test_breaker_open_blocks_new_voice_but_not_text`
- process-restart budget/probe/cooldown gating —
  `test_process_restart_budget_requires_probes_and_caps_restarts`
- text/photo handlers untouched — `test_text_and_photo_handlers_not_part_of_this_module`

## What was NOT done by this worker
- These tests were **not executed inside this response**; this worker has no
  guaranteed live Python execution sandbox with `pytest`/`multiprocessing`
  spawn support in this environment. Per repository precedent
  (task_015/task_021 pattern, see canonical shared memory REC-0009/REC-0011/
  REC-0013), test *authorship* by this worker is not accepted as run
  evidence; an independent controller must execute
  `pytest cloud/task_078_voice_watchdog/tests -v` and report pass/fail
  counts before this package can be marked verified.
- "actual `cars_ui.py` in-memory patch compiles against exact audited SHA"
  cannot be produced because Gate A (live secret-backed GET) was not
  performed in this round — see `gate_a_audit.md`. `installer.py` is written
  to fail closed (refuse to patch) until a real fetched file + matching
  SHA-256 are supplied by whoever executes Gate A.
- No process-restart, no `os._exit`, no live restart, no supervisor probing
  of a real service was performed. `controller.py` only returns decisions;
  it never triggers an exit itself.

## Required next controller step
1. Execute Gate A (fetch the four files + launcher/supervisor manifest,
   record hashes/handler order/current semantics).
2. Run `pytest cloud/task_078_voice_watchdog/tests -v` and record the exact
   pass/fail count in canonical memory (mirroring REC-0013's format).
3. Only after both (1) and (2) are controller-verified, this can move from
   `READY_FOR_CONTROLLER_GATE_A_EXECUTION` to
   `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.

## Current verdict
**FAIL — GATE_A_NOT_EXECUTED** (package ready, live audit and independent
test execution outstanding). Production/CRM live restart remains not fixed
until Gate B is separately, explicitly approved by the owner.
