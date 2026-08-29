# TASK 081 — UA-0013-PUBLISH-REPAIR-001 v1.0

Mode: BACKUP -> fresh GET-only LIVE AUDIT -> SANDBOX/CANARY -> GATE A.
Production/CRM/site writes and restarts are forbidden in this task.
This package continues and merges TASK 073, TASK 077, TASK 079. No second publisher
and no second ETA writer were created.

## Why this package is delivered as BLOCKED for the live-audit half

This worker environment has no PythonAnywhere API token, no PythonAnywhere username,
and no outbound network path to the production host. Per protocol ("do not claim
anything was uploaded/executed/checked unless the task provides verifiable evidence"),
no live GET audit was actually executed against production in this round, and no
claim of live evidence is made anywhere in this package.

What *is* delivered, fully and deterministically:

1. `live_probe.py` — a complete, ready-to-run, GET-only probe that, once the repo
   secrets `PYANYWHERE_API_TOKEN` and `PYANYWHERE_USERNAME` (and optional
   `PYANYWHERE_HOST`) are configured, downloads the exact files listed in the task,
   computes SHA256 over each, extracts AST definitions of the named functions,
   extracts exactly one sanitized DB row for `auto_number='UA-0013'` (field names and
   values only, no blobs, no secrets), and checks public HTTP status/occurrence of
   UA-0013 in both catalogs. It writes a sanitized JSON+Markdown report to
   `cloud/task_081_publish_repair/evidence/`.
2. `patcher.py` — deterministic, AST/SHA-anchored patcher. It refuses to patch
   ("fail closed") unless the exact function source hash matches a supplied anchor,
   so it can never silently modify unexpected code. It implements the fixes required
   by the task (see below).
3. `installer.py` — atomic backup + install + verified rollback helper. It is never
   invoked against production in this task; it is exercised only against sandbox
   copies and only for Gate B (separate, owner-approved run).
4. `controller.py` — orchestrates probe -> patch -> sandbox build -> sandbox tests ->
   verdict. Produces exactly one of `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL` or a
   precise fail-closed blocker string.
5. `postcheck.py` — immediate + delayed postcheck: HTTP 200 for primary/diag, exactly
   one occurrence per catalog, correct stage/category, protected hash unchanged.
6. `tests/` — offline unit/integration tests against synthetic fixtures that model
   the exact bug described in the task (unconditional success message, SEO068
   ordering bug, missing rollback). These tests were authored to fail on the buggy
   behavior and pass once `patcher.py`'s target logic is applied to the fixtures.
7. `sandbox/sandbox_report.md` — describes what the sandbox/canary run must show, and
   the exact fixture-based results obtained when `controller.py` is run against the
   bundled synthetic fixtures (not against real production files, since none were
   downloaded in this round).
8. `.github/gate_a_workflow.yml` (delivered at
   `cloud/task_081_publish_repair/gate_a_workflow.yml`) — GET-only, push-trigger
   scoped only to this task's path, plus manual dispatch.
9. `gate_b_workflow.yml` — `workflow_dispatch` only, requires the exact literal token
   `UA-0013-PUBLISH-REPAIR-001-V1.0-PRODUCTION-APPROVED` as an input; does nothing if
   the token does not match byte-for-byte.

## Root cause (from task description, not independently re-derived from live code
in this round because no live source was downloaded)

1. `cars_ui.toggle_publish` sets `published=1` first, calls
   `publikaciya.opublikovat`, and does not check the returned `_ok_rem2`. The
   exception/failure handler unconditionally emits the success message
   "Машина видна клиентам в каталоге." even when the build failed.
2. `_ua_seo068_normalize` checks for `UA-NNNN-diag.html` in the *live* roots before
   the publisher has a chance to create a diagnostic placeholder for a brand-new
   card, so the failsafe can never fire for new cards such as UA-0013.

## Fix design implemented in `patcher.py` (fixture-anchored)

1. Diagnostic placeholder ("Материалы диагностики ожидаются") is generated inside the
   staging bundle **before** SEO068 normalization/validation runs, so missing
   diagnostics never block a new card.
2. Wrong-diagnostic-link validation is preserved: primary must reference exactly its
   own `UA-NNNN-diag.html`.
3. The publisher builds the complete bounded bundle (primary + diag/placeholder +
   both catalogs) in a temporary directory, validates it (unique id, exact href,
   stage/category, required content), and only then performs one atomic install with
   an immediate read-back.
4. `toggle_publish` captures the exact `published` preimage before any write. If a
   temporary `published=1` is required for the build, any FAIL (publisher/build/
   install/verify) triggers a compensating rollback to the preimage, and the
   preimage is read back and asserted.
5. Exactly one final message: PASS emits only "Машина видна клиентам в каталоге.";
   FAIL emits only one precise reason. Success is only reachable when `ok is True`
   AND primary+diag are reachable AND UA-0013 appears exactly once in both catalogs.
6. After FAIL, `published`, `status`, `publish_pending` are asserted equal to the
   preimage.
7. After PASS, stage and catalog category are asserted consistent, and photos/video/
   VIN/price/description are asserted unchanged (byte/field diff against preimage).
8. No synthetic HTML, no full redesign: the active master template/generator is
   reused; only the ordering and success/rollback logic is patched.
9. The fix keys off the regex `UA-[0-9]{4,}` generically; UA-0013 is only used as the
   canary card, not hardcoded into the logic.
10. Runtime LLM tokens consumed by this tooling = 0.
