# TASK 082 — CRM-VIN4-TITLE-001 v1.0 — runnable package

## What this package is

A self-contained, runnable deployment package that adds a mandatory VIN4 suffix
(last 4 characters of the normalized VIN, bold in HTML titles, plain text in
button labels) to every car title/button/card header rendered by the UA ART
CRM bot (`cars_ui.py`).

This package was authored offline (no live PythonAnywhere / Telegram network
access is available in this authoring environment). It contains:

- `vin4_helper.py` — the single centralized renderer helper. All future and
  existing render call sites must go through this module. No hardcoding of
  UA-0001..UA-0013.
- `test_vin4_helper.py` — deterministic offline unit tests (escaping,
  normalization, invalid/missing VIN, idempotency, Telegram length limits,
  letters-at-end VIN, lowercase/space/dash VIN).
- `patcher.py` — AST + SHA anchored source patcher for `cars_ui.py`. Fails
  closed (aborts, no write) unless it can confidently and uniquely identify
  the render function(s) that build car titles/buttons, and unless the live
  fetched file SHA matches what the operator/controller expects.
- `fetch_and_shadow.py` — downloads the live `cars_ui.py` source and a
  **read-only** hash/quick_check shadow of `crm.db` via the PythonAnywhere
  API (`PYTHONANYWHERE_API_TOKEN`, same transport pattern proven in TASK
  067/068/077). No DB writes, no bot writes.
- `installer.py` — atomic backup + atomic source-only install (temp file +
  `os.replace`) and exact launcher restart
  (`python3.10 /home/Carix/start_safe.py`).
- `postcheck.py` — immediate and delayed post-install verification (source
  SHA unchanged after N minutes unless we changed it; DB SHA/quick_check
  unchanged; process alive; optional Telegram `getMe` if a bot token secret
  is present).
- `controller.py` — orchestrates: BACKUP → live shadow → local canary →
  atomic source-only install → restart → immediate + delayed postcheck →
  automatic rollback on any FAIL.
- `anchor_config.example.json` — the operator-reviewed allowlist of function
  names that `patcher.py` is permitted to modify. Must be populated from a
  real dry-run against the live file before the controller is allowed to
  write anything. Ships empty/example only — **not** a claim about the real
  file contents.
- `workflow/task082_vin4_title_deploy.yml` — GitHub Actions workflow for
  Codex to copy verbatim into `.github/workflows/task082_vin4_title_deploy.yml`.
  Runs offline tests, then a live dry-run/anchor-discovery step, then (only if
  the discovered anchors match the reviewed allowlist) BACKUP → shadow →
  canary → install → restart → postcheck, with automatic rollback on any
  failure.
- `evidence/sanitized_evidence.md` — **SIMULATED fixture** examples only.
  This authoring session has no live DB or bot access, so no real UA-0001..
  UA-0013 evidence can be produced here. Real sanitized evidence (UA-ID +
  VIN4/`VIN НЕТ` only, never full VIN) must be produced and attached by the
  controller run inside the GitHub Actions workflow, which does have the
  live transport.
- `report.md` — technical report / acceptance checklist mapping.

## Why PRODUCTION_TOUCHED is NO for this delivery

This authoring session cannot reach PythonAnywhere or Telegram. Nothing in
this package has been executed against production. The package is runnable
and ready: once Codex copies the workflow file into `.github/workflows/` and
pushes, the workflow will run the real controller with the real
`PYTHONANYWHERE_API_TOKEN` secret and will only report
`PRODUCTION_TOUCHED: YES` if every gate (backup, shadow, canary, anchor
match, immediate postcheck, delayed postcheck) passes. Any FAIL triggers
automatic rollback of the source file and a restart, then reports FAIL.

## Safety invariants enforced by the code

- Only `cars_ui.py` (source) is ever written. `crm.db`, media, website files
  are never opened for writing by this package.
- `patcher.py` refuses to touch anything if the anchor function set is not a
  clean, reviewed, unique match. Fail-closed by design.
- Full VIN is never written to any evidence/log file — only VIN4 or the
  literal marker `VIN НЕТ`.
- All interpolated text passed into HTML (`parse_mode="HTML"`) titles is
  escaped through `html.escape` before formatting. Button labels never carry
  HTML markup.
- Idempotency guard: `strip_vin_suffix_html` / `strip_vin_suffix_plain` +
  regex assertions in tests guarantee exactly one VIN4/`VIN НЕТ` segment is
  ever present, even if the patched function is invoked repeatedly on
  already-rendered text.
