# TASK 094 report — UA-WEB-DESIGN-ROLLBACK-035 v1.0

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Progress checkpoints

- START — task read, owner directive and evidence reviewed. DONE.
- FORENSIC INVENTORY — NOT DONE by this stage. Claude/Cloud has no direct filesystem or API
  access to the live PythonAnywhere account in this environment. A read-only audit script
  (`forensic_audit.py`) was authored and is ready to run, but it has not been executed against
  real production, so no real current hashes for `index.html`/`katalog.html`, and no real TASK
  086 backup hashes, are known to this stage.
- PREIMAGE VERIFIED — NOT DONE. Cannot be done without the forensic inventory step above. Per
  the mandatory fail-closed instruction, this stage does **not** guess, assume, or reconstruct
  the approved design, and does **not** treat the single hash quoted in the task text as
  self-verifying (it must be re-derived by running the audit script against the actual backup
  file).
- RESTORE MAP — a template only (`restore_map.template.json`) is delivered, with every target
  explicitly marked `BLOCKED_AWAITING_FORENSIC_AUDIT`. No hash is fabricated.
- CONTROLLER TESTED — the controller logic (`restore_controller.py`) was authored with hard
  refusal conditions (denylist for CRM/media/DB paths, hash verification before and after
  write, atomic replace, automatic rollback on any `ControllerError`). It has not been executed
  against a live filesystem in this environment, so "tested" here means code-reviewed and
  internally consistent, not run-and-passed against production.
- PRODUCTION BACKUP — NOT DONE (no production write occurred; nothing to back up yet).
- ATOMIC RESTORE — NOT DONE.
- PUBLIC CHECK 1 / PUBLIC CHECK 2 — NOT DONE (two-pass verification module
  `verification_checks.py` is prepared and ready to run once a domain and real content exist to
  check).
- PASS/FAIL — **FAIL-CLOSED / BLOCKED.** The task cannot be marked complete because Phase A
  forensic evidence does not yet exist in this environment. This is the correct, honest outcome
  under the task's own mandatory rule: "Fail closed if the approved preimage cannot be proven."

## What was actually delivered this round

- A complete, reviewable, bounded Phase A/Phase B package under
  `cloud/task_094_web_design_rollback/`:
  - `forensic_audit.py` — read-only hash/size/mtime enumeration of current production files
    and TASK 093/086 backups.
  - `restore_map.template.json` — explicit template, all targets `BLOCKED_AWAITING_FORENSIC_AUDIT`,
    no invented hashes.
  - `restore_controller.py` — zero-LLM deterministic write controller with hard fail-closed
    checks, denylist for CRM/DB/media, atomic write, automatic rollback on any failure.
  - `verification_checks.py` — two-pass public HTTP + content verification (stage order,
    mobile vertical composition marker, all 13 catalog IDs present).
  - `EVIDENCE_REQUIRED.md` — the exact list of real artifacts that must exist before the
    controller is permitted to run.

## What was NOT delivered and why

- No production write occurred. `PRODUCTION_TOUCHED: NO`, as required.
- No real hashes for the current or backup presentation files are reported, because this stage
  has no access to `/home/Carix` in this environment to compute them. Any hash reported without
  that access would be fabricated, which the task explicitly forbids ("No PASS based only on
  script exit code", "Do not invent or reconstruct a design from memory when a verified backup
  exists").
- No claim is made that GitHub Actions success, or any script exit code, means the public site
  is restored, per explicit scope prohibition.

## Required next step

The owner-authorized runner (GitHub Actions job with `PYTHONANYWHERE_API_TOKEN`, or a human
operator with a PythonAnywhere bash console) must:
1. Execute `forensic_audit.py` against real production to produce `audit_report.json`.
2. Have a human/ChatGPT-Codex reviewer inspect `audit_report.json` and the actual backup file
   contents to select the verified preimage and fill in `restore_map.json` accordingly (using
   `restore_map.template.json` as the schema).
3. Execute `restore_controller.py` with the completed `restore_map.json`.
4. Execute `verification_checks.py` twice (built into the controller) and retain
   `evidence_<run_id>.json` as the acceptance evidence.

Only after that sequence produces real, verifiable evidence can TASK 094 be marked DONE.
