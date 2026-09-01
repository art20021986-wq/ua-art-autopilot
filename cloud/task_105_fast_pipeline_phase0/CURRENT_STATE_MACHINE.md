# CURRENT STATE MACHINE — TASK105

## Observed problem

The repository has 129 workflow files with overlapping status vocabularies. Historical tasks use
`DONE`, `PASS`, `100%`, `WAITING_OWNER`, `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL`,
workflow `success`, and production verification as different notions of completion.

## Current composite flow

```text
TASK CREATED
  → WORKFLOW TRIGGERED
  → AI/DESIGN/REPAIR OUTPUT CREATED
  → SANDBOX OR GATE A PASS
  → POSSIBLY WAITING OWNER
  → GATE B / PRODUCTION
  → POSSIBLY LIVE VERIFY
  → REPORT
```

The defect is that several intermediate states are presented as “finished”.

## Canonical replacement state machine

```text
QUEUED
  → CLASSIFYING
  → RUNNING
  → TESTING
  → READY_FOR_DEPLOY
  → DEPLOYING
  → VERIFYING
  → FINISHED
```

Exceptional terminal/holding states:

- `BLOCKED`: a resolvable external or owner dependency exists.
- `FAILED`: deterministic execution failed and no safe retry remains.
- `ROLLED_BACK`: attempted production change was reversed and rollback verified.

## Hard semantic rules

- `PASS` describes a test, never the whole task.
- `100%` is forbidden unless status is `FINISHED`.
- `WAITING_OWNER` is not finished.
- `GATE_A_PASS_AWAITING_PRODUCTION_APPROVAL` maps to `READY_FOR_DEPLOY`.
- Workflow conclusion `success` means only that the workflow completed its own steps.
- `FINISHED` requires a final receipt proving the requested target environment and business result.
