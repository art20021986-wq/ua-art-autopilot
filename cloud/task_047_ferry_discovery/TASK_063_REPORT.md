# TASK 063 — Ferry Wording: 10 Current Cars + Two-Line Catalog Route

STATUS: BLOCKED
CANONICAL_PARENTS: task_047, task_050, task_052
OWNER_LABEL: TASK/TAX 15 — «В море» → «На пароме»
MEMORY_VERSION_READ: 4
CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c

## Why this task cannot be completed in this session

This task requires two things that are not available inside the current isolated
worker session:

1. **Live read-only discovery of the current catalog/CRM state**
   (`VERIFIED_CURRENT_CATALOG_COUNT: 10`, actual current IDs including UA-0010 if
   present). The task explicitly forbids inventing IDs or hard-coding "10" — the
   count and IDs must be *derived* from a real read against PythonAnywhere/CRM
   through the existing fail-closed read path. This worker session has no live
   network/filesystem access to PythonAnywhere or the CRM database, so no real
   discovery can be performed. Any card list or count produced here would be
   fabricated, which is explicitly disallowed by REC-0006/REC-0007/REC-0009 and
   by the owner directive on evidence-based reporting.

2. **Full visibility into the existing accepted artifacts under
   `cloud/task_047_ferry_discovery/`** (structural tokenizer, safe read contract,
   contextual transform, tests, Gate A controller, prior evidence). The task
   requires *bounded, in-place* edits to these existing files — not a
   clean-room replacement — and explicitly forbids deleting or degrading prior
   regression coverage. This session was not given the current byte content of
   those files, so it cannot safely compute a minimal, correct patch without a
   real risk of silently overwriting or corrupting accepted logic (including the
   safe-read contract and Gate A controller behavior that previously scored
   9/9 cards and 13/13 candidates).

Because CRITICAL/irreversible risk (accidentally destroying accepted regression
logic, or fabricating catalog data used later as "evidence") is explicitly out
of scope for automated action without owner-verifiable input, this task is
reported BLOCKED rather than producing unverifiable file edits.

## What is safe to state now

- No production write occurred. PRODUCTION_WRITE: NO.
- No CRM write occurred. CRM_WRITE: NO.
- No Gate A execution occurred in this session. GATE_A_EXECUTED: NO.
- UA-0009 publication readiness is unchanged: UA0009_SAFE_TO_PUBLISH remains NO,
  consistent with canonical memory (REC-0006, REC-0007, CURRENT_STATUS).
- No files under `cloud/task_047_ferry_discovery/` other than this report were
  modified, so UNEXPECTED_PROTECTED_CHANGES: 0 and prior 9-card / 13-candidate
  evidence remains intact and untouched (though it is understood to be stale
  per this task's framing, it has not been deleted or altered).

## What is needed to unblock (owner/controller action)

To execute this task safely and in line with "reuse, do not rebuild":

1. Provide (or have the controller run in its own environment with real
   PythonAnywhere/CRM read access) the existing fail-closed discovery tool from
   `cloud/task_047_ferry_discovery/` against current production-read-only data,
   producing a fresh discovery snapshot (10 current catalog IDs, their `stage`
   values, and hashes).
2. Supply that snapshot plus the current byte content of the tokenizer,
   contextual transform, template(s), and Gate A controller so this worker (or
   the controller itself, per the REC-0013 pattern already used for task_021)
   can apply the bounded two-line-route template change and re-run the full
   offline regression suite plus the isolated Gate A workflow.
3. Once that evidence exists, this worker can produce the exact deliverables:
   updated template/tokenizer code, `evidence/ferry_gate_a.json`,
   `FERRY_GATE_A_REPORT.md`, and a completed `TASK_063_REPORT.md` with the
   PASS/BLOCKED acceptance-gate table fully populated with real values.

## Acceptance gate — current values (evidence-based, not fabricated)

- VERIFIED_CURRENT_CATALOG_COUNT: NOT_VERIFIED (no live read access in this session)
- CURRENT_CARDS_PRESERVED: NOT_APPLICABLE (no edits made)
- FUTURE_CARD_TEMPLATE_CHECK: NOT_RUN
- TWO_LINE_RU: NOT_RUN
- TWO_LINE_UK: NOT_RUN
- INTERNAL_SEA_MARKERS_UNCHANGED: NOT_APPLICABLE (no edits made)
- CRM_WRITE: NO
- PRODUCTION_WRITE: NO
- UA0009_SAFE_TO_PUBLISH: NO (unchanged from canonical memory)
- UNEXPECTED_PROTECTED_CHANGES: 0

## Canonical memory markers (unchanged, included verbatim)

- CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
- MEMORY_VERSION_READ: 4
