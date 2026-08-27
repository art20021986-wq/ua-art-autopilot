# PRODUCTION_PATCH_PLAN.md — TASK_016 (Gate B preview only, not executed)

This plan describes what a future, explicitly authorized Gate B would
do. It is documentation only. No file in this task performs any of the
steps below. Gate B requires separate explicit owner CRITICAL approval.

## Preconditions before Gate B may even be proposed

1. Gate A receipt (`gate_a_receipt.json`) shows:
   - `deterministic_10x: true`
   - `protected_unchanged: true`
   - `final_status: "AWAITING_GATE_B"`
2. A reachable preview URL exists and has been visually confirmed.
3. All nine real UA-0001..UA-0009 cards pass the full `TEST_MATRIX.md`.
4. Owner has reviewed the preview and explicitly authorized Gate B in
   writing.

## Gate B steps (NOT executed by this task)

1. Snapshot/backup current production UA-0001..UA-0009 and CRM state.
2. Apply the verified diff (legacy control removal + two unified
   buttons + companion page links) to each real card file individually,
   one at a time, with a hash-verified before/after diff review.
3. Re-run the full validation suite against the live copies in a
   maintenance window.
4. Only after explicit owner go-ahead, consider UA-0009 publication as
   a separate, later authorization — never bundled with Gate B card
   patching.
5. WSGI reload only if functionally required and only with owner
   sign-off, performed by the owner's own deployment process, not by
   this worker.

## Rollback plan

Every patched file must have a timestamped backup copy retained under
a non-public path before modification, restorable via a single
`os.replace` per file.
