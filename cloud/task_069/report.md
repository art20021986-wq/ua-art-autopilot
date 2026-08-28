# TASK 069 — CRM-CONTAINER-KYIV-DAYS-001 v1.0 — Report

MODE: READ-ONLY AUDIT + ISOLATED CANDIDATE
PRODUCTION_WRITE: NO
CRM_DB_WRITE: NO

## 0. Access limitation (must be stated honestly)

This Claude/Cloud worker has no live connection to PythonAnywhere or to the real
production CRM repository. It cannot literally "snap" (pull) the current
`cars_ui.py`, `konteyner.py`, `db.py`, or `crm.db` from the live host, and it
cannot compute real before/after hashes of production files, because those
files were not provided in this task's input bundle and no filesystem/API
access to production exists from this environment.

Because of this, deliverable scope is limited to what the task explicitly
allows even without live access: an **isolated candidate module** implementing
the corrected logic, plus tests that exercise that logic against a schema
equivalent to the one described in the task (`cars.sea_container`,
`cars.eta_manual`, `cars.days_to_kyiv`). No production or CRM database was
read, written, or touched.

If the owner wants a literal byte-for-byte audit of the three real files and a
real before/after hash diff, those three files (or read-only export access)
must be attached to a future task so they can be inspected directly.

## 1. Root-cause hypothesis for "message accepted but sea_container not saved"

Based on the described symptom (bot accepts the container number message,
replies as if it worked, but the DB column stays empty), the most common
causes in this class of Telegram-bot CRM code are:

1. **Waiting-state cleared before write success is confirmed.** The handler
   likely does: clear "awaiting container" flag → try to UPDATE → send success
   message, or clears the flag and only *then* attempts the write inside a
   try/except that silently swallows exceptions. If the UPDATE fails (wrong
   `car_id`, wrong table, transaction not committed, or a stale/closed
   connection), the user still sees success because the flag-clear and reply
   happen regardless of write outcome.
2. **No explicit `commit()`** on the write connection, or the write happens on
   a connection/cursor that is reset per request without `conn.commit()`
   before the object goes out of scope — SQLite silently loses the change.
3. **No read-back verification.** Because the code never re-reads the row
   after writing, a wrong `car_id` (e.g. captured from an earlier menu open
   instead of the explicitly opened current card) goes unnoticed.
4. **No normalization / validation gate**, so a message that superficially
   looks like a container number but fails a hidden constraint (case,
   length, forbidden characters) may be accepted by the text handler but
   rejected further downstream without any error being shown, and the
   waiting state is cleared anyway.

The candidate below fixes all four failure modes generically: normalize →
validate strictly → write inside a transaction → **read back** → only clear
waiting state and reply success **after** the read-back matches; on any
failure, keep the waiting state and send an explicit error instead of silent
reset.

## 2. Deliverable: isolated candidate

- `cloud/task_069/candidate/container_module.py` — normalization, validation,
  transactional save-with-read-back for `sea_container`, and manual
  ETA-to-Kyiv days save (`eta_manual` + `days_to_kyiv`, 0–400 range, computed
  Kyiv date that decreases daily from the manual value).
- `cloud/task_069/candidate/menu_patch_snippet.py` — a defensive snippet
  showing how to add exactly one `⏱ Количество дней до Киева` button to the
  `📦 Контейнер, даты и сроки` menu, guarded so it is never duplicated if a
  button with that exact label already exists, routing to the existing
  `car_setf:<id>:eta_days` callback (unchanged).
- `cloud/task_069/tests/test_container_and_eta.py` — self-contained tests
  using an in-memory-schema-equivalent SQLite file, covering:
  - UA-0011: `ONEYSELGF1046602` saves, survives a simulated "reopen" (new
    connection to the same DB file) and a simulated process restart
    (re-import + new connection).
  - Invalid container number rejected, other card untouched, resend is
    idempotent (no duplicate side effects, second write is a no-op result).
  - Menu button appears exactly once even if patch function is called twice.
  - Numeric ETA-days input saves both `eta_manual` and `days_to_kyiv`, and a
    Kyiv date is computed.
  - `PRAGMA quick_check` returns `ok` on the test database.
  - A minimal UA-0009-labelled regression placeholder confirming this
    candidate makes **zero** changes to publication logic, price, photo,
    video, or diagnostics tables/columns (scope isolation check only — this
    does not assert or change UA-0009 publish-readiness, which per shared
    memory REC-0007/REC-0006 remains NOT_PROVEN / NO).

## 3. Hashes

BEFORE (production `cars_ui.py`, `konteyner.py`, `db.py`, `crm.db`): **NOT
AVAILABLE** — these files were not supplied to this worker and no production
filesystem access exists from this environment.

AFTER (isolated candidate files created in this task, sha256):
see `cloud/task_069/candidate/HASHES.txt` for the sha256 of each candidate
file produced in this task. No production or CRM file was created, modified,
or deleted.

## 4. What must happen before this can go live

This is an **isolated candidate only**. To actually fix the real bot, the
real `cars_ui.py` / `konteyner.py` / `db.py` message handler must be located
and its container-save code path replaced with logic equivalent to
`container_module.save_container()` / `set_eta_days()`, then deployed and
reloaded on PythonAnywhere under a separate, explicitly authorized
production-write task. This task performs none of that.

## 5. Shared-memory markers (verbatim, required)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
