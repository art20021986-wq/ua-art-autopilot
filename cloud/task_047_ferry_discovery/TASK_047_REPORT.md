# TASK 047 REPORT — Ferry Wording Phase 1

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## What was requested

The owner asked for a full automatic replacement of "В море" with "На
пароме" system-wide (9 cards and all future ones). TASK 045 attempted a
broad implementation but failed a Python static check before any commit
happened, so nothing from TASK 045 exists in the repository. TASK 047
re-scopes this into a small, verifiable phase-1 slice per the owner's
parent-task chain (042/043/045).

## What this phase delivers

1. `transform.py` — a self-contained, dependency-free contextual text
   transform engine implementing the exact RU/UA mapping table from the
   task (status/long/heading/short forms), with fail-closed handling of
   ambiguous standalone `Море`.
2. `discover.py` — a bounded, fail-closed, read-only discovery tool for
   the exact registry of candidate files (video/site pages, UA-0001..
   UA-0009 candidates, the named Python modules, and `crm.db`), plus a
   read-only, schema-allowlisted CRM inspection routine.
3. Full `unittest` coverage for both modules (see `tests/`), runnable via
   `run_tests.py`, which also enforces `py_compile` success for every
   Python file in this package — directly addressing the TASK 045
   failure mode.

## What this phase does NOT do

- It does not touch production, the live site, CRM, `crm.db`, or any card.
- It does not execute on PythonAnywhere.
- It does not implement Gate A, a network controller, or a workflow.
- It does not publish UA-0009.
- It does not perform real discovery against the live `/home/Carix`
  filesystem from within this sandbox — `discover.py` is delivered ready
  to run there, but no such run has occurred, and no results from a real
  run are claimed.

## Honesty on scope limits

The HTML transform is a targeted tag/text tokenizer, not a full HTML5
parser. It correctly handles every case explicitly required by TASK 047
(one-line spans, nested elements, data-ru/data-uk pairs, quote variants,
void elements, uppercase tags, entities, comments, script/style, and
ordinary prose), and this is verified by the included tests. It is not
claimed to handle arbitrary malformed HTML beyond that scope.

Discovery's fail-closed read path (containment, symlink checks, lstat,
O_NOFOLLOW, nlink check, fstat before/after, size bound, strict UTF-8,
full-byte SHA-256) and the CRM read-only routine (URI mode=ro,
query_only=ON, quick_check, allowlisted schema, exact UA-0001..UA-0009
lookups, identity-unchanged verification) are implemented and tested
against temporary local fixtures, since no real production file or
database was available or permitted to be touched in this environment.

## Safety markers

PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
UA0009_SAFE_TO_PUBLISH: NO

## Status

READY_FOR_CODEX_PHASE1_AUDIT
