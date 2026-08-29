# TASK 082 report — CRM-VIN4-TITLE-001 v1.0

## Scope delivered

- Centralized, deterministic VIN4 render helper (`vin4_helper.py`) covering:
  title HTML (`VIN <b>XXXX</b>` / `<b>VIN НЕТ</b>`), button plain-text label
  (`VIN XXXX` / `VIN НЕТ`, no markup).
- 20 deterministic offline unit tests (`test_vin4_helper.py`) covering:
  normalization (case/spaces/dashes), 17-char charset validity
  (`[A-HJ-NPR-Z0-9]`), VIN ending in a letter, missing/None/invalid VIN,
  HTML injection/escaping, exactly-one-bold assertion, idempotency (no
  double `VIN` suffix on re-render), Telegram button length truncation,
  no-full-VIN-leak assertion, and a future UA-9999 fixture.
- AST + SHA anchored patcher (`patcher.py`) that is fail-closed: it will not
  modify `cars_ui.py` unless (a) it can find render-function candidates by
  conservative heuristics, and (b) an operator-reviewed `anchor_config.json`
  (populated from a real live dry-run, not the shipped example file) matches
  those candidates by name and exact source SHA256.
- Read-only live fetch + DB shadow (`fetch_and_shadow.py`) using the proven
  `PYTHONANYWHERE_API_TOKEN` transport (TASK 067/068/077 pattern). No DB
  write path exists in this module.
- Backup + atomic source-only install + exact launcher restart
  (`installer.py`, `python3.10 /home/Carix/start_safe.py` restarted via the
  PythonAnywhere always-on-task restart endpoint).
- Immediate + delayed postcheck (`postcheck.py`): source SHA match, DB
  SHA/quick_check unchanged, optional Telegram `getMe`, and a delayed
  re-check (default 5 minutes) to catch a later generator overwriting the
  patch.
- Orchestrating controller (`controller.py`) implementing exactly:
  BACKUP → live shadow → local canary → atomic source-only install →
  restart → immediate + delayed postcheck → automatic rollback on any FAIL.
- GitHub Actions workflow template for Codex to install
  (`workflow/task082_vin4_title_deploy.yml`).

## What has NOT happened (and why)

This authoring session has no live network access to PythonAnywhere or
Telegram. Therefore:

- No live fetch of the real `cars_ui.py` was performed here, so the real
  render-function names/SHAs are unknown to this session and
  `anchor_config.example.json` is an explicit template, not a claim.
- No backup path, before/after SHA, or real sanitized 13-row evidence exists
  yet — `evidence/sanitized_evidence.md` is explicitly labeled as a
  simulated fixture demonstration of the output *format* only.
- No installer/restart/postcheck has run against production.
- `PRODUCTION_TOUCHED: NO` for this delivery, per protocol (never claim
  execution without verifiable evidence).

## What happens next (mechanical, no further owner decision needed)

1. Codex copies `workflow/task082_vin4_title_deploy.yml` to
   `.github/workflows/task082_vin4_title_deploy.yml` and pushes.
2. The `offline_tests` job runs the deterministic suite (must be 100% green
   before anything live is touched).
3. The `live_deploy` job runs `controller.py`, which fetches the real live
   source, discovers render-function candidates, and currently will
   correctly **FAIL CLOSED** (`anchor_config.json missing`) because no
   reviewed allowlist exists yet — this is intentional and safe. A follow-up
   run (or the same run, if the allowlist-population step is added by Codex
   using the discovered-candidates dry-run output) must populate the real
   `anchor_config.json` with the true function name(s) and SHA256 before the
   patch step can proceed.
4. Once the allowlist is reviewed and present, the same workflow performs
   BACKUP → shadow → canary → install → restart → postcheck automatically,
   and reports PASS/FAIL with rollback already applied on FAIL.

## Acceptance checklist mapping

| Acceptance item | Status |
|---|---|
| 13/13 rows show exactly one VIN4 or `VIN НЕТ` | Format proven by tests + simulated fixture; real 13 rows pending live CI run |
| UA-9999 fixture passes same helper | PASS (test + fixture doc) |
| Exactly one bold VIN4 in HTML; no markup in button, exactly one VIN4 | PASS (unit tests) |
| HTML escaping/injection, case/spaces/dashes, letter-ending VIN, invalid/missing, idempotency, Telegram limits | PASS (unit tests) |
| getMe/launcher health before & after | Implemented in postcheck.py; pending live CI run |
| crm.db SHA/quick_check, media, website hashes unchanged | Implemented as a hard gate in postcheck.py; pending live CI run |
| Only cars_ui.py changed, minimal exact set | Enforced fail-closed by patcher.py's anchor verification |
| Delayed check confirms no overwrite | Implemented (`delayed_postcheck`, default 300s) |
| Backup path + before/after SHA + 13 sanitized examples reported | Will be emitted by controller.py on the real run; simulated examples included now for format review |
