# TASK 121 — UA-ART-UA0017-PUBLISH-ONLY-001 v1.0

## Owner approval
Approved by owner on 2026-09-08: prepare publication of **UA-0017 only** in a separate branch and present Gate B. **Do not modify Production. Do not modify UA-0018 or any other card. Production requires a later explicit owner command: `ПУБЛИКОВАТЬ UA-0017`.**

## Branch scope
This task is prepared on branch `ua0017-publish-only-001`, based on main commit `af683ac6236dcbf7a70e56183de7134d5af4b6b7`.

## Verified prior incident
TASK120 (`TASK120-PUBLISH-UA-0017-UA-0018`) ended with semantic outcome `ABORTED_NO_PRODUCTION_WRITE`. The backup job failed with `MUTATING_ALWAYS_ON_UNAVAILABLE`; the temporary Always-On POST returned no usable trigger id. No backup mode, install-mode controller, card/CRM/media/public-site write, rollback controller, or final receipt executed. The prior task therefore did not publish UA-0017 or UA-0018.

## Goal
Prepare a verifiable, fail-closed, **single-card** execution package for UA-0017 and a Gate B report. No Production write is allowed in this task.

## Target
- Card: `UA-0017`
- Existing authenticated CRM target from TASK120 reference only:
  - internal id: 26
  - VIN: `WAUZZZ4GXGN069684`
  - brand/model: Audi A6
  - CRM year: 2015
  - mileage: 118000 km
  - current referenced status: `ge_waiting`
  - referenced media: 39 JPEG photos, 0 video
- These values MUST be re-verified from the authenticated CRM snapshot before any future Production command. They are not authority to overwrite newer CRM data.

## Hard exclusions
1. UA-0018 must not be read as a publication target or changed.
2. No other card may be changed.
3. No Production database flag, catalog file, public page, media asset, DNS/TLS setting, runtime source, or shared design region may be modified.
4. No VIN advertising, third-party VIN widget, generic fallback specification, or untrusted HTML injection.
5. Do not reuse TASK120 as a two-card transaction.
6. Do not interpret the prior owner authorization for TASK120 as authorization for this task.
7. Do not bypass a missing Always-On capability by weakening safety gates or using an unapproved scheduled-task fallback.

## Required preparation
### A. Read-only live verification
Before Gate B, obtain a fresh authenticated read-only snapshot for UA-0017 and verify:
- exact CRM row identity and VIN;
- year, price, mileage, engine/fuel/gearbox/drive, stage/status;
- publication flags and current catalog presence;
- complete UA-0017 media binding and actual media count;
- current additional-specification rows and their provenance;
- public state of the existing 16-card catalog and UA-0016 as a non-target control;
- available storage and current transport/runtime capability relevant to a future single-card publish.

### B. Specification integrity
The prior TASK120 reference contained 18 legacy model-level rows for UA-0017, derived from a 2016 Audi source document while the CRM vehicle year is 2015. Do not claim those rows as VIN-specific or as verified equipment of this exact vehicle unless independently supported. Separate verified vehicle facts from model-level reference facts. Do not invent rows to reach a target count.

### C. Single-card execution package
A future executable package must be newly bound to this task and UA-0017 only. It must not merely rename TASK120 while retaining UA-0018 constants, paths, backup scope, receipts, catalog assertions, or transaction semantics.

Required properties:
- one-card target set: UA-0017 only;
- fresh-preimage/CAS guard for any future publication flag mutation;
- byte-exact or content-addressed backup of the exact UA-0017-owned change set before any future write;
- fail-closed rendering and public post-verification;
- rollback limited to this task-owned UA-0017 mutation set;
- preservation of shared logs without truncation;
- no Production execution path enabled before a new explicit owner authorization;
- no durable temporary trigger/process after success;
- if temporary execution capability cannot be created/stopped safely, return BLOCKED without Production mutation.

## Provenance rule
Executable/source deliverables must comply with `cloud/claude_provenance_lock.md`: ChatGPT/Codex may author this task specification and audit outputs, but must not present self-authored executable files as Claude deliverables. Any new executable under `cloud/` intended as a working project file must have verified allowed provenance before Gate B can be PASS.

## Gate B acceptance criteria
Gate B may be `PASS` only when all are true:
1. Branch scope is single-card UA-0017.
2. Fresh read-only CRM/media/spec/public snapshot is recorded.
3. New single-card package exists and passes its tests without Production write.
4. Package contains no UA-0018 target/mutation path.
5. Backup and rollback scope is UA-0017-only plus minimal shared catalog metadata required for atomic publication.
6. Additional specification is truthful about provenance and 2015/2016 mismatch.
7. Production authorization for this task is absent.
8. The prior TASK120 Always-On failure is either demonstrably resolved for the future Production path or the package has an explicitly approved safe execution mechanism; no bypass.
9. Non-target change count = 0 in sandbox/preview comparison.

## Gate B output
Produce a short owner-facing report with:
- root cause of TASK120 failure;
- branch and exact commit SHA;
- fresh UA-0017 snapshot summary;
- package provenance and file hashes;
- test results;
- preview evidence if available;
- explicit list of future Production paths that would change;
- explicit confirmation: UA-0018 changes = 0;
- final Gate B status: PASS or HOLD/BLOCKED with one concrete blocker.

## Production lock
This task is **PREPARATION ONLY**. Do not publish. Future Production requires a new task-bound authorization created only after the owner sends exactly the intended command `ПУБЛИКОВАТЬ UA-0017` or an unambiguous equivalent that explicitly authorizes this single-card production operation.
