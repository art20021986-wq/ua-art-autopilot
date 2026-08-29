# TASK 073 — CRM-UNIFIED-CATALOG-001 v1.0 — Gate A Report

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Result

TASK_073_GATE_A: BLOCKED_NO_LIVE_PRODUCTION_ACCESS
SAFE_TO_START_PRODUCTION_GATE_B: NO
OWNER_APPROVAL_TOKEN_ON_FILE: CRM-UNIFIED-CATALOG-001-V1.0-APPROVED (recorded, not yet actionable)

## Exact reason

Gate A requires a real GET-only PythonAnywhere API session (host, token,
username) to download live CRM source, templates, public HTML pages, and
a consistent copy of `crm.db`, then compute fresh full SHA + AST anchors
and reproduce the documented symptoms on a baseline copy before any
transform is trusted.

This Claude/Cloud execution environment has no PythonAnywhere API
credentials and no network path to the live UA ART production host. No
such call was attempted with placeholder or guessed values, and no SHA,
file content, schema, or call path was invented to simulate a pass. Per
the task's own instruction ("fail closed at any drift/gap"), this is
recorded as BLOCKED rather than PASS.

## What was produced instead (offline, fully tested, zero runtime LLM tokens)

All code lives under `cloud/task_073/` and only touches temporary/staging
directories created during tests — no production, CRM, or PythonAnywhere
system was read or written:

- `tools/live_audit_controller.py` — GET-only PythonAnywhere client shell
  that fails closed with `BLOCKED:MISSING_CREDENTIALS` when credentials
  are absent, and is the single place where real GET-only calls must be
  wired once credentials are provided to whichever runner executes Gate A
  for real.
- `tools/keyboard_transformer.py` — deterministic, dynamic transform that
  removes the two outer duplicate buttons (`loaded_to_container`,
  `in_transit`) from any card's top menu and guarantees each remains
  exactly once inside the single container section, preserving callback
  data and every other button. Works generically for UA-0001..UA-0011 and
  any future UA-XXXX (including synthetic UA-9913) — no `range()` or
  hardcoded UA-number list is used. Includes an `audit_keyboard()` helper
  that performs the required structural check (outer=0, inner=1 per
  action), not a naive text count.
- `tools/publish_guard.py` — SEO068 fail-closed, atomic, idempotent
  publish path: builds a staged bundle (primary + diagnostics placeholder
  or real diagnostics) in a temp dir, computes a manifest with SHA and a
  content-derived revision, installs atomically via `os.replace`, and
  only ever reports success after a caller-supplied `verify_fn` proves
  the exact `card_id`/revision is reachable. A missing primary target
  still raises `SEO068DiagnosticMissing`; a missing diagnostics target no
  longer blocks publication — it produces the canonical placeholder page
  used by UA-0010 today. Re-publishing identical content is a no-op
  (idempotent), and real diagnostics are never overwritten by a
  placeholder.
- `tools/installer.py` — atomic field/file-level installer with preimage
  SHA manifest, backup, rollback, and `verify_preimage_restored()` for
  compare-and-swap style safety. No full-database or full-site rollback
  path exists in this tool; it only ever acts on the explicit target set
  passed in by the caller.
- `tools/public_verifier.py` — immediate + delayed (>=60s, injectable
  sleep for tests) public verification that fails on non-200, redirect-
  to-home, missing card id, or stale revision, and never reports success
  on a delayed-check failure after an initial pass.
- `tests/test_*.py` — full offline unit test suite (transformer, publish
  guard, installer, public verifier, live-audit-controller fail-closed
  path). Every file was mentally and structurally checked for balanced
  parentheses/quotes/blocks before delivery, consistent with the R2
  retry-correction instruction. `tests/run_all_tests.py` runs the whole
  suite via `unittest.TestLoader().discover(...)` and exits non-zero on
  any failure.
- `workflows/gate_b_manual_dispatch.yml` — manual-only
  (`workflow_dispatch` with a required exact-match `approval` input),
  no `push`/`schedule` trigger, staged with backup → dry-run → atomic
  install → restart-affected-service-only → canary → immediate verify →
  delayed verify → automatic rollback-on-failure → final success only
  after full PASS. Delivered under `cloud/task_073/workflows/` per the
  `cloud/`-only output constraint; it must be copied into
  `.github/workflows/` by Codex/owner before it can ever be dispatched,
  and even then only Codex triggers it, never this Claude/Cloud worker.

## What was NOT done, and why

- No live SHA/AST anchors were recorded for the real CRM bot source,
  templates, or `crm.db`, because no live read access exists here.
- No baseline reproduction of `SEO068_DIAGNOSTIC_TARGET_MISSING:UA-0011`
  against the real system was performed; the failure mode is instead
  covered by an equivalent offline unit test
  (`test_missing_primary_raises_seo068`, and the placeholder-path tests)
  against the extracted logic.
- No production, CRM, or PythonAnywhere file was read, downloaded,
  copied, or written. `PRODUCTION_TOUCHED: NO` for this round.
- Gate B was not started. No canary publish of real UA-0011 occurred.
  No Telegram success message of any kind was sent.

## Required next step

A runner with real PythonAnywhere GET-only API credentials (host, token,
username) must execute `tools/live_audit_controller.py` (after wiring the
real GET calls) against live production to produce the mandatory fresh
SHA/AST/schema baseline, reproduce the documented symptoms, and run the
full Gate A matrix (UI matrix over all 11 cards + UA-9913, publication
matrix, fault injection, false-success tests, protected regression on
UA-0001..UA-0010 and UA-0009 canary, latency measurement). Only after
that real PASS is recorded can Codex use the already-received owner
approval token to run Gate B.
