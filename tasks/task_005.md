# TASK 005 — UA-0009 FINAL NON-PRODUCTION COMPLETION PACKAGE

MODE: READ_ONLY
MAX_ROUNDS: 10

## Owner outcome

The owner needs UA-0009 ready for work in the morning with the fewest possible manual actions. Complete every remaining NON-PRODUCTION step in one coherent package. Do not publish and do not change crm.db or any production site file. The only unavoidable owner action after this task should be one authorized run on PythonAnywhere followed by one visual YES/NO and, later, a separate explicit CRITICAL publication approval.

Do not repeat completed TASK 003 work. Treat TASK 004 as a prototype that must be hardened before live execution.

## Confirmed UA-0009 facts

- auto_number: UA-0009
- VIN: KNAGU416BJA242741
- make/model/year: Kia K5 2018
- fuel: gas/LPG, CRM value previously reported as газ
- engine: 2000 cm3
- mileage: 300000 km
- published: 0 / draft
- production publication is currently blocked
- UA-0001 through UA-0008 must remain byte-identical

## Known unresolved gates

- No real PythonAnywhere TASK_004 final report exists yet.
- The real duplicate topology is not yet proven.
- Previous evidence showed UA-0009 sandbox HTML exists, but OBD UA-0009, synthetic OBD UA-0010, and NEW CARD SAFETY previously failed.
- The current state/current_status.md is stale and must not be trusted as the live task source.
- cloud/latest_status.md is the handoff source, but its old timestamp must be corrected.
- Missing fields may include transmission, drivetrain, color, price, and stage/status, but the runner must recover them automatically before asking the owner.

## Mandatory correction of TASK 004 prototype risks

The replacement runner must fix every item below:

1. Enforce realpath containment for every writable path.
2. Refuse any writable directory or target that is a symlink.
3. Use atomic writes with fsync and os.replace for sandbox files and reports.
4. HTML-escape every value recovered from CRM or HTML before rendering.
5. Never copy or open an untrusted seed HTML as an executable review page. Preserve it only as escaped text evidence or a byte copy clearly marked DO_NOT_OPEN if needed.
6. Quote SQLite identifiers safely and use URI mode=ro plus PRAGMA query_only=ON. Issue only SELECT and read-only PRAGMA statements.
7. Print safe duplicate evidence: table, rowid or primary key, auto_number, VIN, published/status. Do not print unrelated fields or customer PII.
8. Re-discover protected files after the run and detect modifications, additions, deletions, and path changes. Do not compare only the original path list.
9. Include shared protected production files from the established baseline or release-gate manifest, not only filenames containing UA-0001 through UA-0008.
10. Never report DATABASE_CHANGED: NO or PRODUCTION_SITE_FILES_CHANGED: 0 unless supported by measured before/after evidence. If proof is unavailable, report NOT_PROVEN and fail the gate.
11. SAFE_FOR_OWNER_VISUAL_REVIEW must be NO if any of these occur: SQLite quick_check FAIL, duplicate classification MORE_PROOF_NEEDED or TRUE_DUPLICATE, protected manifest mismatch, invalid HTML, unsafe/broken local reference, duplicate diagnostic CTA, unresolved OBD/new-card-safety failure, sandbox creation failure, or a missing critical draft field.
12. UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE must reflect all required draft fields, not merely hardcoded identity constants.
13. Do not call a bare text-only HTML page a production-equivalent visual preview. Reuse the approved structure/style only when it can be proven from the newest UA-0009 sandbox and current protected source. If a faithful isolated preview cannot be built safely, stop and report the exact blocker.
14. Never use shell=True, os.system, subprocess, eval, exec, network calls, imports of production generators, WSGI reloads, service restarts, schedule changes, or dynamic code loading.
15. Keep the job light. No media conversion, no database dump, no broad unrelated filesystem crawl. Stop with DEFERRED_CPU_LIMIT if a reliable configured CPU-limit signal indicates 85 percent or more; otherwise state CPU_LIMIT_NOT_PROVEN without inventing a PASS.

## Single hardened PythonAnywhere runner

Create cloud/ua0009_finish_runner.py, Python 3.10 standard library only.

When an authorized operator runs it on PythonAnywhere, it must do all of the following in one run:

### Phase A — preflight and write-boundary proof

- Resolve and validate all paths.
- Allowed writes only:
  - /home/Carix/sandbox_ua0009_finish/video/*
  - /home/Carix/video/ua0009_finish_report.txt
  - /home/Carix/video/ua0009_finish_report.json
- Refuse symlinks, traversal, non-regular overwrite targets, and any resolved path outside those exact roots.
- Capture a before manifest for crm.db metadata and hash where safe, UA-0001 through UA-0008 files, established protected shared files, and relevant source/generator files.
- Do not create any production HTML/media or alter existing production files.

### Phase B — live CRM and duplicate proof

- Open /home/Carix/crm.db strictly read-only.
- Run quick_check.
- Find all exact UA-0009 and VIN matches with safe identifier evidence.
- Classify SAME_ROW_COUNTING_ARTIFACT, MULTI_TABLE_REFERENCE_NOT_DUPLICATE, TRUE_DUPLICATE, or MORE_PROOF_NEEDED.
- TRUE_DUPLICATE and MORE_PROOF_NEEDED must block readiness.
- Recover UA-0009-only fields without borrowing any vehicle facts from UA-0001 through UA-0008.

### Phase C — actual new-card compatibility checks

Prove all of:

- UA-0009 can be represented without changing existing card data.
- The card generator or approved structure is not hard-limited to 1 through 8.
- A synthetic UA-0010 dry-run in a disposable sandbox passes, proving the fix is not special-cased only for 0009.
- Existing UA-0001 through UA-0008 remain unchanged.
- No duplicate diagnostic CTA.
- No empty img/video/source href/src.
- No broken local references required by the preview.
- OBD/diagnostic behavior follows the approved conditional rule: show only when real UA-specific evidence exists; never fabricate a report or link.
- Two video slots are never populated by the same file hash.
- Mobile and desktop HTML structure remains compatible with the approved current card template.
- No fake reviews, undocumented promises, fake scarcity, false discounts, or unsupported vehicle claims are introduced.

### Phase D — faithful isolated sandbox

- Use only UA-0009 evidence.
- Build a reviewable card and diagnostics page under /home/Carix/sandbox_ua0009_finish/video/.
- Preserve approved current layout/style when safely recoverable.
- Missing noncritical values must visibly say Уточняется.
- Do not emit broken media placeholders.
- Generate the sandbox 10 times in disposable temporary directories and compare normalized deterministic hashes. Require 10/10 PASS.
- The final preserved sandbox must be the verified deterministic output.

### Phase E — after-state proof

- Capture a fresh after manifest.
- Compare modifications, additions, deletions, and hashes.
- Require exact unchanged results for crm.db, UA-0001 through UA-0008, protected shared files, source/generator files, WSGI, and schedules.
- The two permitted report files are the only writes under /home/Carix/video.
- Report all facts honestly; do not hardcode PASS values.

## Reports

The runner must write both human-readable TXT and machine-readable JSON reports with the same facts.

Mandatory final block:

TASK_ID: task_005
MODE: READ_ONLY
SQLITE_QUICK_CHECK: PASS/FAIL
DUPLICATE_CLASSIFICATION: ...
DUPLICATE_EVIDENCE: ...
UA0009_EXISTS_IN_CRM: YES/NO
UA0009_FIELDS_RECOVERED: ...
UA0009_OWNER_INPUT_REQUIRED: ...
UA0009_REQUIRED_DRAFT_FIELDS_COMPLETE: YES/NO
UA0009_OBD_RULE: PASS/FAIL
UA0010_SYNTHETIC_NEW_CARD_TEST: PASS/FAIL
SANDBOX_10_RUNS: PASS/FAIL
UA0009_SANDBOX_CREATED: YES/NO
UA0009_CARD_PATH: ...
UA0009_DIAG_PATH: ...
HTML_VALIDATION: PASS/FAIL
MEDIA_VALIDATION: PASS/FAIL
UA0001_0008_UNCHANGED: PASS/FAIL
PROTECTED_SHARED_FILES_UNCHANGED: PASS/FAIL/NOT_PROVEN
DATABASE_UNCHANGED: PASS/FAIL/NOT_PROVEN
PRODUCTION_SITE_FILES_CHANGED: 0 or exact count
UNEXPECTED_CHANGES: NONE or exact paths
PRODUCTION_WRITE_PERFORMED: NO
SAFE_FOR_OWNER_VISUAL_REVIEW: YES/NO
SAFE_TO_PUBLISH_UA0009_NOW: NO
OWNER_VISUAL_CHECK_REQUIRED: YES/NO
OWNER_APPROVAL_REQUIRED: NO
NEXT_ACTION: one exact sentence
STATUS: WAITING_VISUAL_CHECK/STOPPED

## Morning owner instructions

Create cloud/ua0009_morning_instructions.md containing only:

- exact file to upload or pull
- exact PythonAnywhere path
- exact Run command/button action
- expected duration
- exact report paths
- one sandbox URL/path to inspect
- what result means STOP
- what result means ready for visual YES/NO
- no production publish instruction

The instructions must fit on one mobile screen where practical.

## Conditional publication plan

Create cloud/ua0009_publication_plan.md. This is documentation only, not an executable production patch.

It must state the exact later CRITICAL gates:

1. TASK 005 live report fully green.
2. Owner supplies only fields still missing.
3. Owner visual approval YES.
4. A separate production payload is built from the verified sandbox.
5. Backup, explicit whitelist, rollback rehearsal, tests, and zero unexpected changes all PASS.
6. Owner gives a separate explicit APPROVE command.
7. Atomic publication followed by HTTP/mobile/desktop/catalog/card/diagnostics checks.
8. Immediate rollback on any FAIL.

List the smallest expected production whitelist, but do not guess paths that cannot be proven from repository evidence; mark them TO_BE_RESOLVED_FROM_LIVE_REPORT.

## Deliverables

Create or update every file:

1. cloud/ua0009_finish_runner.py
2. cloud/ua0009_finish_spec.md
3. cloud/ua0009_morning_instructions.md
4. cloud/ua0009_publication_plan.md
5. cloud/cloud_report_005.md
6. cloud/latest_status.md

## Cloud verification before DONE

- The GitHub worker must compile every Python file.
- Perform a line-by-line static safety review.
- Prove all writable paths are constant, contained, non-symlink, and atomic.
- Prove no database write statement exists.
- Prove no production generator/import/reload/publish code exists.
- Prove report PASS values are computed, not hardcoded.
- Correct UPDATED_AT_UTC to the real current UTC time.
- If any mandatory item cannot be proven, return BLOCKED with the exact issue; do not claim DONE.

## Hard stop

This task prepares one safe live gate and a production plan. It must never publish UA-0009, change CRM, alter UA-0001 through UA-0008, or perform any CRITICAL action.
