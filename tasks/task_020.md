# TASK 020 — OWNER-APPROVED REAL-INPUT GATE A DRY RUN

OWNER_CONFIRMATION: «Подтверждаю»
OWNER_CONFIRMATION_UTC: 2026-08-27T11:38:17Z
PARENT_TASKS: task_014, task_017, task_018, task_019
MODE: GATE_A_REAL_INPUTS_READ_ONLY
PRODUCTION_WRITE: FORBIDDEN
CRM_WRITE: FORBIDDEN
GATE_B: FORBIDDEN
WSGI_RELOAD: FORBIDDEN
LIVE_UA0009_PUBLICATION: FORBIDDEN

## Owner authorization

The owner authorizes the pipeline to read the real bounded UA ART card/CRM/generator inputs required for a Gate A dry run and to create isolated preview, report, manifest, hash and receipt artifacts only under the previously approved Gate A report/receipt namespaces.

This authorization is **not** permission to modify production cards, shared production pages, generators, CRM/database contents, media sources, WSGI configuration, scheduled production jobs, or to perform Gate B. Gate B remains locked behind a separate future explicit owner approval.

## Mandatory ordering gate

Before remote Gate A execution, the controller must independently run the TASK 019 Shared Memory acceptance suite and healthcheck. Any failure blocks execution. Do not invent PASS evidence.

## Authoritative specification

TASK 017 is authoritative. TASK 018's generic `data/input_cards/*.json` placeholder pipeline is not an acceptable substitute for TASK 017 and must not be used to claim real Gate A completion.

## Mandatory implementation action

Create an actually executable Python 3.10+ stdlib-only remote Gate A package under `cloud/ua_cards_unified/` for delivery to:
`/home/Carix/autopilot_inbox/cloud/ua_cards_unified/`

The package must include a no-argument restricted launcher and bounded read-only preflight/runner. It must:

1. Run only from the exact safe-inbox directory above.
2. Accept no CLI arguments and reject path/action environment overrides.
3. Discover only the explicit bounded real paths from TASK 017; never recursively scan the account.
4. Require real source HTML for UA-0001…UA-0008; never synthesize/demo those cards.
5. Evaluate UA-0009 only from actual source/CRM/generator evidence; otherwise mark publication readiness BLOCKED.
6. Open CRM/database and generator sources read-only. Never execute imported production generators and never write to them.
7. Hash every bound input and protected production path before running.
8. Create preview copies and companion diagnostic/tracking pages only under:
   `/home/Carix/video/reports/ua_cards_unified/preview/`
9. Write reports only under:
   `/home/Carix/video/reports/ua_cards_unified/`
10. Write the machine-readable receipt only under:
    `/home/Carix/ua_cards_unified_gate_a_receipt/`
11. Require exactly one purchase anchor whose class tokens include both `dejstvie` and `kn_kupit`; never guess an insertion point.
12. Normalize preview output to exactly one card-specific diagnostics link `{CODE}-diag.html` and one card-specific tracking link `{CODE}-track.html`, immediately before the purchase anchor.
13. Preserve unrelated HTML, existing safe carrier URLs and real evidence. Never invent VIN, mileage, diagnostics, carrier, container, status or auction facts.
14. Use an honest explicit empty state when real diagnostic/tracking data is absent.
15. Validate local links/media using the approved real source roots from TASK 017 and reject traversal/escape/symlinks.
16. Perform deterministic second generation and require byte-identical output.
17. Any per-card failure blocks overall `AWAITING_GATE_B`.
18. Re-hash every protected path after execution and require zero unexpected protected changes.
19. Never contain a production-apply function, production target, webapp reload call, or Gate B branch.
20. Emit real, machine-readable manifest, per-card results, protected before/after hashes, output hashes, progress state and receipt. Do not claim 100% from code generation alone.

## Required deliverables

Use these exact deliverables so the automatic controller can find them:

- `cloud/ua_cards_unified/gate_a_task020_common.py`
- `cloud/ua_cards_unified/gate_a_task020_preflight.py`
- `cloud/ua_cards_unified/gate_a_task020_runner.py`
- `cloud/ua_cards_unified/gate_a_task020_launcher.py`
- `cloud/ua_cards_unified/GATE_A_TASK020_OPERATOR.md`
- `cloud/ua_cards_unified/gate_a_task020_contract.json`
- `cloud/ua_cards_unified/tests/test_gate_a_task020.py`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

The launcher filename and path are contractual. The post-sync controller will invoke exactly:
`python3.10 /home/Carix/autopilot_inbox/cloud/ua_cards_unified/gate_a_task020_launcher.py`
with no arguments.

## Exact remote output contract

The automatic controller accepts results only at these exact paths:

- `/home/Carix/ua_cards_unified_gate_a_receipt/task_020_gate_a_receipt.json`
- `/home/Carix/video/reports/ua_cards_unified/task_020_manifest.json`
- `/home/Carix/video/reports/ua_cards_unified/task_020_results.json`
- `/home/Carix/video/reports/ua_cards_unified/task_020_protected_hashes.json`
- `/home/Carix/video/reports/ua_cards_unified/progress.json`
- `/home/Carix/video/reports/ua_cards_unified/latest_status.html`
- `/home/Carix/video/reports/ua_cards_unified/preview/index.html`

The receipt must include at minimum:

- `task_id: task_020`
- `mode: GATE_A_REAL_INPUTS_READ_ONLY`
- `gate_status: BLOCKED` or `AWAITING_GATE_B`
- `production_write: false`
- `crm_write: false`
- `gate_b_executed: false`
- `wsgi_reloaded: false`
- `ua0009_published: false`
- `unexpected_protected_changes: 0`
- exact manifest SHA-256, runner SHA-256, input hashes and output hashes
- per-card UA-0001…UA-0009 status and exact blockers

Write the receipt atomically and only after protected before/after hashes have been compared. A missing/malformed field is a hard controller failure.

## Required final status fields

`cloud/latest_status.md` must state:

- TASK_ID: task_020
- CLAUDE_STATUS
- FILES_CREATED
- PRODUCTION_TOUCHED: NO
- CRM_TOUCHED: NO
- GATE_B_EXECUTED: NO
- OWNER_ACTION_REQUIRED: NO unless a real external blocker is proven
- NEXT_FOR_CHATGPT: independent tests, safe-inbox sync, then remote Gate A execution

Do not modify production, CRM, WSGI, live cards or the existing website in this GitHub task. Focus output budget on complete executable code, not explanation.