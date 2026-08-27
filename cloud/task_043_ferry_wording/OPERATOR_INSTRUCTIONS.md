# TASK 043 — Operator / controller instructions (for later, approved, real execution)

These instructions are for whoever (Codex, or a human operator) is authorized to wire `controller.py` to a real PythonAnywhere API client. **Do not execute any of this until `controller.py` and `workflow_template.yml` have been independently audited.**

## Preconditions

1. `PYTHONANYWHERE_API_TOKEN` is present as a GitHub Actions secret, never printed or logged.
2. Account is exactly `Carix`; host is exactly `www.pythonanywhere.com` or `eu.pythonanywhere.com`.
3. The safe-inbox sync manifest binds the exact SHA-256 of `discover.py` and `gate_a.py` as actually copied onto PythonAnywhere. Use `controller.verify_manifest(manifest, expected_hashes)` before triggering anything.

## Step 1 — Real read-only discovery

1. Copy `discover.py` and `transform.py` into the PythonAnywhere safe-inbox location, verify their SHA-256 against the manifest.
2. Trigger `python3 discover.py` (no arguments; it defaults to `/home/Carix`) via the controller's `run_discovery(...)`.
3. Poll for the receipt JSON at the exact expected path.
4. Validate: strict JSON, no duplicate keys, no secret-shaped terms, `production_touched`/`crm_touched`/`gate_b_executed` all `NO`.
5. Persist the validated receipt under `cloud/task_043_ferry_wording/evidence/discovery_receipt.json` in a follow-up commit — do not fabricate this file without a real receipt.

## Step 2 — Isolated Gate A

1. Using only paths present in the discovery receipt, invoke `gate_a.build_gate_a(...)` (via the controller's `run_gate_a`) targeting only:
   - `/home/Carix/video/preview/task-043-ferry-wording/`
   - `/home/Carix/video/reports/task-043-ferry-wording/`
   - `/home/Carix/autopilot_runs/task_043_ferry_wording/`
2. Confirm two independent builds produce identical `sha_after` per file, and `determinism_check` reports a single hash across 10 runs.
3. Fetch the public preview/report URLs and confirm HTTP 200. This proves the *preview* is reachable, never that production changed.

## Step 3 — Reporting

1. Commit the real receipts, manifest, and per-card matrix under `cloud/task_043_ferry_wording/evidence/`.
2. Update `cloud/latest_status.md` to `READY_FOR_REAL_GATE_A` or `AWAITING_GATE_B` only if every check above genuinely passed.
3. Do not advance to Gate B without explicit owner approval in a new task.

## What is forbidden at every step

- Any write outside the three approved roots.
- Any call to a reload/restart/Gate-B/publish/vacuum/attach endpoint.
- Any CRM or `crm.db` write.
- Any UA-0009 publication.
