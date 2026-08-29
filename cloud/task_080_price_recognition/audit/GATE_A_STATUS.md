# TASK 080 — Gate A Audit Status

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Requirement
Gate A requires a fresh live GET of `cars_ui.py`, `local_ocr.py`, `ai_fast_schema.py`,
`ai_filter.py`, and the active price writer from the live CRM/PythonAnywhere host,
plus whole-file and active-function SHA-256 anchors, before any patch may be
considered eligible for Gate B.

## Result of this round
This Claude/Cloud worker has no live network/tool access to the PythonAnywhere
host inside this delivery channel. No live GET of `cars_ui.py`, `local_ocr.py`,
`ai_fast_schema.py`, `ai_filter.py`, or the active price writer was performed.
No SHA-256 anchors of live files were computed. Consequently:

- No in-memory patch may be applied against live code in this round.
- The shared deterministic parser below is a **prepared candidate only**,
  designed against the defect description and prior evidence
  (`cloud/task_065/evidence/voice_path.json`) and the acceptance formats
  listed in the task.
- The narrow patcher (`src/patcher.py`) is hash-gated: it refuses to touch any
  target file unless it is given the exact freshly-computed SHA-256 of that
  file's current live content and the active function name it expects to
  replace. Until a controller with live GET access supplies those hashes,
  the patcher will always fail closed.

## Fail-closed statement
This task cannot be marked `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.
The correct outcome for this round is:

`FAIL_CLOSED_NO_LIVE_GATE_A_ACCESS_IN_THIS_DELIVERY_CHANNEL`

No production, crm.db, public site, or Telegram process was read or touched.
No runtime LLM tokens were used. No card was created, duplicated, or modified.

## What ChatGPT/Codex controller must do next
1. Run the live GET audit of the five files above from an environment that has
   access to the CRM host, exactly as Gate A requires.
2. Compute whole-file SHA-256 and the SHA-256 of the active function bodies
   for: `cars_ui.catch_message`, `local_ocr.fields_from_text`,
   `ai_fast_schema.fast_text_data` / `labeled_text_data`, `ai_filter`'s
   relevant filter function, and the active price-writer function.
3. Feed those hashes into `src/patcher.py` as the `expected_hashes` manifest.
4. Re-run `tests/test_price_parser.py` in a real Python environment (this
   round only desk-checked the logic manually; see `TEST_RESULTS.md`).
5. Only after (1)-(4) succeed, resubmit for narrow SANDBOX/CANARY patch
   construction and a separately authorized Gate B.
