# UA-0002 Stage A review pack — NOT READY

The user approved UA-ART-UA0002-CRITICAL-DELETE-001 v1.0, stages A and B. This draft preserves that authorization (`gate_b_authorized=true`). It does not require renewed owner consent. Missing factual safety evidence and unfinished exact launch binding block execution.

No external write, launch, production installation, deletion or provider task was performed while authoring this pack. The controller additionally refuses any manifest whose `readiness` is not `READY_FOR_APPROVED_EXECUTION`.

## Contents and verified facts

- `cloud/ua0002_delete_a/`: three canonical adapters, seven immutable remote worker files, three test modules and four public HTML fixtures.
- `tasks/requests/UA-ART-UA0002-CRITICAL-DELETE-A-001.json`: hash-bound draft request.
- `tasks/manifests/`, `tasks/gates/`, `tasks/approvals/`: NOT_READY scope, current approved owner scope, source/page pins and pending exact launch bindings.
- `LOCAL_VALIDATION.json`: 35 local tests PASS (11 adapter, 12 worker, 12 lifecycle) plus syntax checks. These are local fixture results, not live acceptance.
- `REVIEW_PACK.json`: exact candidate hashes and outstanding blockers.
- `build_review_pack.py`: deterministic review-draft hash builder. It always preserves NOT_READY and never creates a launch or storage observation.

Actual source/public-file pins come from GET-only run 35524475591, finished 2026-09-20T17:01:47Z. Additional exact provider/source facts come from run 35525152538, finished 2026-09-20T17:14:20Z. A future installation must re-read and match these pins.

## Exact remote scope

Only seven files and `plan.json` may be uploaded into `/home/Carix/autopilot_inbox/cloud/ua0002_delete_a/<numeric-run-id>/`: `remote_stage_a.py`, `remote_lifecycle.py`, `publication_fence.py`, `visibility_lifecycle.py`, `ua_site_counters.py`, `uaart_price_sync_runtime.py`, and `provenance.json`. Result files are read only. The API adapter allows these task files and `always_on/`; it refuses production-path uploads and provider PATCH operations. The remote lifecycle separately controls only the exact known CRM supervisor after writer admission.

The task can create its own exact-described worker. Cleanup checks its ID, full command and description and requires an exact-plan terminal `safe_to_stop` receipt. A terminal failure is cleaned up and still fails acceptance; unknown and nonterminal workers remain untouched.

Stage A requires UA-0002's current CRM row to be absent and the actual matching deletion audit to exist. An existing row, including a hidden one, requires Stage B's durable tombstone first. No CRM row, source media or production Python file is changed by Stage A.

## Truthful recovery semantics

The approved recovery keeps the sold vehicle retired. It restores safe non-target invariants by forward completion, never by restoring the original listing or whole database. The manifest explicitly binds the canonical `restored=true` field to that meaning. A separate `FORWARD-RECOVERY` evidence artifact records the actual worker evidence, original phase error code when applicable, and live public checks.

A failed first phase followed by proven forward retirement may be accepted only when target absence, unchanged database/other pages, zero media writes, checksum/integrity checks, and CRM Running are all proven, followed by real HTTP acceptance. Otherwise no PASS receipt is written. Public checks require 404/410 for target routes and exact hash-matched 200 for catalog, home and sitemap.

## Unresolved factual gates

1. Fresh PythonAnywhere account quota is unavailable. No storage evidence file exists here; old observations are not relabeled. Host disk free space is not account quota.
2. A reviewed fresh provider/OS writer inventory and future schedule quiet window remain required. Current GET metadata is not OS process proof.
3. Current target row absence, matching audit, database integrity and exact alias inventory remain live admission facts to collect before mutation.
4. Independent final package review remains open; this pack does not mark Gate A PASS.
5. The canonical workflow's known missing nonce reservation during generic rollback reconstruction remains a documented limitation. This worker performs durable forward recovery itself; a complete accepted recovery route must be verified before launch.
6. Exact launch nonce, expiration, approved request subject binding and future admission values must be filled from real facts. No launch marker is supplied.

The draft request deliberately fails executable readiness. Do not substitute fake quota, Gate A PASS or a reused launch to make it pass.
