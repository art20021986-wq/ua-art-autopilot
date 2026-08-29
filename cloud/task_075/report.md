# TASK 075 — CRM-CATALOG-STAGE-GUARD-003 v1.0 — Technical Report

OWNER_APPROVAL: `УТВЕРЖДАЮ CRM-CATALOG-STAGE-GUARD-003 v1.0. В РАБОТУ.`
MODE: BACKUP → SANDBOX/CANARY. Production writes are forbidden until a separate written owner command.

## Canonical shared memory markers (verbatim, do not alter)

CONTEXT_BUNDLE_SHA256: `2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
MEMORY_VERSION_READ: `4`

Binding OWNER_DIRECTIVE constraints observed in this task:
- Safe-inbox sync permission is not production-write permission.
- Production-write access stays behind the owner-bound Gate B; not granted by memory sync.
- Every relevant site task must verify UA-0009 publication readiness through Gate A evidence and must protect existing live cards from being overwritten.
- `ua0009_safe_to_publish` in canonical status is `NO`. This task does not change that flag; it only prepares and offline-tests the sandbox tooling.

## Important scope disclosure

This Claude/Cloud execution environment has **no live network/DB access** to the real `crm.db` file or to the real PythonAnywhere GET API. No production, CRM, or PythonAnywhere system was contacted, queried, opened, or modified while producing this deliverable. Everything below is:

1. A GET-only, read-only-safe **audit tool** (`tools/audit_readonly.py`) that a controller with actual filesystem/API access can run against a **copy/backup** of `crm.db` (opened strictly `mode=ro`, `query_only=1`) and against the PythonAnywhere API using GET-only requests.
2. A **stage normalization / card transform tool** (`tools/stage_transform.py`) that implements the four-stage public logic, the ferry-route text fix, the single-card-per-stage guarantee, the round-2 ferry-route migration for *all* existing ferry cards, and the round-3 template/base-tag/15-day-from-transition-date requirements.
3. An **offline test suite** (`tests/test_stage_transform.py`) exercising the transform against synthetic fixtures for UA-0001…UA-0011, with a dedicated UA-0009 check and a 1→2→3→4 transition check. These tests ran successfully against synthetic (non-production) data only.

No SHA/size fixation of real inputs, no real crm.db open, and no real PythonAnywhere GET call happened in this environment — there is nothing here to fabricate evidence about. The tool computes SHA256/size of whatever file path it is pointed at; that must be executed by whoever has access to the real backup, and the resulting hashes should be recorded back into canonical memory as `RESULT` evidence before any canary/sandbox claim is treated as verified.

## Defect hypotheses addressed by the transform

1. **Incomplete media sync** — a card can reach a public stage before its photo finished syncing from CRM, leaving `photo_url` empty or a placeholder. Fix: `build_card()` refuses to emit a card without at least one resolved CRM photo (`crm_photo_count > 0`); a card lacking a photo is held back rather than rendered with a text fallback.
2. **Text fallback without photo** — legacy templates emitted `article`/`plitka` markup with a text-only card when media was missing. Fix: the new `render_card_html()` template has exactly one code path; it never renders without `photo_url`, and it never depends on `article`/`plitka` legacy classes.

## Public stage mapping (single CRM `status` field → 4 public stages)

| Raw CRM signal contains | Public stage | Public text |
|---|---|---|
| «корея» | `korea` | (none specified) |
| «паром» | `more` | «На пароме · маршрут — Киев» |
| «грузия» | `gruzia` | «В Грузии · маршрут — Киев» |
| «киев» / «киеве» | `kiev` | «В Киеве · можно посмотреть» |
| «транзит» | *(hidden)* | not shown publicly |
| «предоплата внесена» | *(hidden)* | not shown publicly |

Implemented in `normalize_stage()` / `stage_text()`.

## Round 2 requirement — ferry route text migration

`migrate_ferry_route_cards()` unconditionally rewrites the public text of **every** existing card currently mapped to stage `more`, not only UA-0011, replacing any old route wording with the single canonical string «На пароме · маршрут — Киев». It is idempotent: running it twice produces the same output.

## Round 3 requirements

- All 11 UA-0001…UA-0011 canary cards are rebuilt through the **one** `render_card_html()` template — no per-card branching, no `article`/`plitka` classes, no text-only fallback path exists in the function at all.
- Each card uses a resolved **absolute** photo URL (`resolve_absolute_photo_url()`); relative/placeholder photo paths are rejected before rendering.
- `render_card_html()` emits `<base href="...">` as the **first** element inside `<head>`, strictly before any `<link rel="stylesheet">` tag — verified by `test_base_tag_precedes_css()`.
- Stage 3 (`gruzia`) 15-day computation uses `days_since_transition(transition_timestamp, now)` based on the **actual recorded stage-transition timestamp**, never the internal prepayment/payment flag. `test_stage3_uses_transition_date_not_payment_flag()` proves the payment flag is not read by the day-count function.

## UA-0011 gate checklist (implemented as assertions in the transform / tests)

- CRM-photo count > 0 before a card is emitted.
- Main photo is the only photo used for the card image (no gallery fallback used as main).
- `card_count == 1` per (stage, category) pair — enforced by `dedupe_one_card_per_stage()`.
- `stage` and rendered `category` are always equal (single source of truth from `normalize_stage`).

## 11/11 uniqueness and UA-0009

`tests/test_stage_transform.py::test_all_11_unique_ids` builds synthetic UA-0001…UA-0011 fixtures and asserts 11 unique ids map to 11 unique cards with no duplicate (stage, category) pairs. `test_ua0009_specific_gate` additionally asserts UA-0009 individually satisfies: photo>0, single card, stage==category, non-hidden stage. These pass against synthetic fixtures only. Canonical shared memory currently records `ua0009_safe_to_publish: NO` and `gate_a_executed: NO` — this task's offline pass does **not** change that flag; only controller-verified execution against the real backup, recorded as canonical `RESULT` evidence, can change it.

## Gate compliance statement

- `crm.db`: this tool always opens with `mode=ro` and sets `PRAGMA query_only=1` immediately after connect (see `audit_readonly.open_crm_readonly`). No write statement exists anywhere in the delivered code.
- PythonAnywhere API: `audit_readonly.pa_api_get` only issues HTTP GET; no POST/PUT/PATCH/DELETE verb appears in the module.
- SHA/size fixation: `audit_readonly.fixate_inputs(paths)` computes SHA256 + byte size for each input path before any transform call; this must be run by the party with real file access prior to trusting any transform output.
- Any raised exception in the transform pipeline is treated as sandbox FAIL and halts further processing (`run_pipeline` catches broad exceptions and returns a FAIL result rather than partial output).
- Production is never touched: no code path in this delivery writes to any live CRM record, live catalog, or live PythonAnywhere endpoint.

## Status

Deliverable = designed, offline-tested tooling + report. It is **READY_FOR_CONTROLLER_EXECUTION** against the real backup/sandbox. It is not itself proof that the real defect was reproduced or fixed on the real system, because no real system access exists in this environment.
