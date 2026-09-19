# TASK088: watchdog target HALT and current workflow contracts

Status: **CANDIDATE / NOT ACTIVATED / GATE B NOT PASSED**.

This package is based on exact main `0c85a6561d80c4d8789b3a482ae41cdaf9d0f667`. It contains source patches and offline regression tests, not a deployment receipt. Main, PythonAnywhere, CRM and the website were not modified.

## Confirmed problems

- Maintenance [run 34747832918](https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/34747832918) failed seven outdated workflow assertions. The current recovery route has eight writers (six bounded-retry writers and two fixed-parent CAS writers), a tightly scoped read-only Actions queue token step, and stricter single-parent autostart checks.
- Watchdog [run 34751097747](https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/34751097747) attempted the historical TASK120 recovery canary despite absence of its target HALT. The historical receipt correctly rejected changed runtime bindings. Rewriting that receipt would conceal the mismatch and is not a fix.

## Changes

`runtime-and-contracts.patch` changes exactly two tracked files; `candidate_manifest.json` records their before/after SHA-256 values.

1. Watchdog discovery checks the exact committed historical TASK120 HALT before its scheduled recovery canary. Absence in both HEAD and the working tree produces `false`, and the obsolete canary is skipped. The exact target produces `true`, retaining all original runtime/receipt checks. Other, malformed, untracked, changed, oversized or symlink HALT files fail closed. Active transaction handling is unchanged.
2. Workflow contracts now describe the actual strict runtime. Negative cases reject changed owner/repository/ref/run/operation/plan scope, token endpoint/method/shell additions, repeated CAS pushes, changed parents, rebases and missing readback. The autostart parent gate is executed as actual shell and rejects merges, root commits and wrong parents.

Only the watchdog discovery job and the scheduled canary condition change. The canary implementation, recovery execution, rollback jobs, core Python, runtime manifest and old receipts remain byte-identical to the base.

## Verification — 13 September 2026

| Verification | Result |
| --- | --- |
| Owner policy and price captions, including Ukrainian certification | 47/47 PASS |
| Extracted target-HALT guard against isolated Git repositories | 13/13 PASS |
| Contract repair alone against original exact main workflow/manifest | 183/183 PASS; no skips |
| Contracts with the changed candidate watchdog and old immutable pins | 37/38 PASS; 1 expected binding ERROR |
| Full suite with changed watchdog and old immutable pins | 162/183 PASS; 1 FAIL and 20 ERROR, all 21 caused by watchdog hash binding |
| Patch whitespace and reverse application check | PASS |

The 183/183 result proves the seven original contract failures are repaired. It does **not** certify the changed watchdog for live execution. The combined candidate is deliberately not declared green: its runtime binding and activation gates are still outstanding.

## Offline reproduction

Use an isolated checkout at the exact base commit, with this package copied into the same `cloud/` path. Do not execute production workflows.

```bash
git apply --check cloud/task088_watchdog_target_halt/runtime-and-contracts.patch
git apply --include=automation/packages/task107_r2/test_workflow_contracts.py cloud/task088_watchdog_target_halt/runtime-and-contracts.patch
python3 -I -m unittest discover -s automation/packages/task107_r2 -p 'test_*.py' -v
git apply --include=.github/workflows/uaart_transaction_watchdog.yml cloud/task088_watchdog_target_halt/runtime-and-contracts.patch
python3 -I -m unittest discover -s cloud/task088_watchdog_target_halt -p 'test_*.py' -v
```

The first suite must pass 183/183 against the original workflow. The guard suite must pass 13/13 after applying the watchdog patch. Running the full suite at that point still rejects the candidate SHA until legitimate separate activation.

## Installation blockers

Prepare a fresh candidate runtime binding and carry it through the existing reviewed activation procedure, preserving historical receipts. Recheck current main, open claims/transactions, external writers and actual owner authorization before any production action. A new source commit or conflicting change invalidates these base assumptions.

Gate B must establish correct no-HALT behavior, unchanged protections for an actual target HALT, current runtime acceptance and safe recovery. Never dispatch old TASK120 or Stage 2 requests to test this patch, manufacture receipts, remove a real HALT, or update old hashes merely to make tests pass.

Stage 2 already has its canonical successful receipt. This package does not repeat Stage 2, install site Stage 3, certify Stage 4, connect Telegram delivery, or prove the 60-second publication SLA. Those remain distinct integration and live-acceptance work.
