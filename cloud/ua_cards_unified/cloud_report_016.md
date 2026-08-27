# cloud_report_016.md

## TASK
task_016 — resume and complete task_014 with PythonAnywhere Gate A, after
the non-fast-forward push failure that stopped task_014's outputs from
landing.

## What changed vs the TASK 013 candidate and the interrupted TASK 014 attempt

1. Real CRM discovery via a small hardcoded candidate list, opened
   strictly read-only (`mode=ro`, `PRAGMA query_only=ON`, `quick_check`
   gate before any query).
2. Explicit field alias allowlist; unmapped/absent values always render
   as `Уточняется` (or `NOT_PROVEN` for provenance fields), never
   invented.
3. Real card HTML discovery via a small hardcoded candidate list per
   code, read-only; production generators are only hashed for
   before/after protection, never imported or executed.
4. Legacy diagnostic/tracking control removal via a documented pattern
   set (`LEGACY_CONFLICT_AUDIT.md`) prior to inserting exactly one
   unified diagnostics button and one unified tracking button at a
   single, unambiguous structural anchor; ambiguous anchors fail closed
   per-card instead of guessing.
5. Removal of the previously unverified hardcoded poster path; posters
   now must pass containment/type/hash checks or fall back to a locally
   generated SVG placeholder written only inside the preview root.
6. A 10x full-sequence determinism loop over the real nine codes,
   comparing canonical JSON hashes of the run results before any
   preview is considered exposable.
7. Atomic writes (`tempfile` + `fsync` + `os.replace`) for every output
   file, confined by `assert_write_allowed()` to exactly three
   non-public sandbox roots.
8. `build_gate_a_manifest.py` now hashes an exact hardcoded file set
   under the safe inbox path, refuses missing/symlink/zero-byte/
   unexpected files, sets `target_mode: SANDBOX_ONLY`, `gate_a: true`,
   `gate_b: false`, and prints the manifest SHA-256.
9. `RUN_GATE_A_TASK016.py` is the single, argument-free, location-
   verified entrypoint that chains the manifest builder and the
   launcher in restricted mode, refusing environment overrides that
   would broaden scope, and emits a machine-readable receipt.

## What could not be verified from this worker

This worker has no direct execution channel onto PythonAnywhere. It
cannot itself confirm that the real CRM file exists at one of the
hardcoded candidate paths, that real UA-0001..UA-0009 HTML matches the
assumed anchor convention, or that a preview URL is reachable. See
`BLOCKED.md` for the precise, honest blocker and the safe next action
that does not require any manual owner upload.

## Safety statement

No file in this delivery writes to production, CRM, live cards, or
generators. No WSGI reload is triggered. No UA-0009 publication occurs.
All writes are gated to three hardcoded non-public roots and validated
by `assert_write_allowed()` before every write.

PRODUCTION_TOUCHED: NO
