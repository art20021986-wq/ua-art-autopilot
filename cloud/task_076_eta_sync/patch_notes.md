# Integration notes — wiring the release candidate into real production files

This package was built without direct access to the real contents of
`db.py`, `konteyner.py`, `stranica.py`, `master_card.py`, `yadro.py`, and
`publikaciya.py` (no GET access from this sandbox). It therefore cannot ship
as a literal diff against those files. Instead it defines exact integration
points; a controller/owner session with real repo access should apply these
under Gate A verification before any Gate B run.

## 1. `db.py` / low-level CRM access

- Replace whatever currently handles an incoming `eta_days` callback with a
  call into `eta_transaction.EtaSyncController.submit(car_id, days)`.
- Wire `DbAdapter` to the real schema using `sqlite_adapter_reference.py` as
  a starting point, after confirming table/column names via Gate A
  read-only `PRAGMA table_info` (never write during that check).
- Do not perform a full DB file replace. Only the row-level `UPDATE` inside
  `BEGIN IMMEDIATE` shown in the reference adapter is acceptable.

## 2. `konteyner.py` (catalog rendering)

- Wherever the catalog currently reads `days_to_kyiv` / `eta_manual` per
  card, replace that direct field read with
  `eta_engine.resolve_eta(manual_eta_object, stage_fallback_object)` so the
  catalog and the card page always agree, using the identical priority
  order (manual > stage rule > neutral).
- `PublishAdapter.rebuild_catalogs()` should call the existing catalog
  regeneration function(s) for BOTH catalog surfaces referenced in the task
  (two catalog directories).

## 3. `stranica.py` / `master_card.py` (card page rendering)

- Card page ETA block: same `resolve_eta(...)` call, single formatting
  function producing `eta.display_date()`.
- Free-text description: before writing/rendering it, run
  `eta_engine.strip_stale_dates(description)`. This only removes an
  independent absolute calendar date; it does not touch VIN, price, photos,
  video, design, or stage text.
- `PublishAdapter.rebuild_card(car_id)` should call the existing single-card
  rebuild/regeneration function, plus the required diag/placeholder
  regeneration if the live system has one for this card.

## 4. `yadro.py` (core/orchestration)

- If `yadro.py` currently owns the callback wiring for `eta_days` (per the
  task: "callback `eta_days` → validation → сохранение обоих ETA-полей →
  verified read-back → bounded rebuild/publish → оба `/video` и `/site` →
  public HTTP"), that whole chain should become a single call to
  `EtaSyncController.submit(car_id, days)` and returning its
  `TransactionResult` to the CRM UI. CRM must show "success" only when
  `result.success is True`; otherwise it must show `result.error` and keep
  the retry job (`controller.has_pending_retry(car_id)` /
  `controller.process_retries()`).

## 5. `publikaciya.py` (publisher)

- Implement the real `PublishAdapter`:
  - `rebuild_card(car_id)` → existing per-card generator, return `True`
    only on a verified successful file write (not just "no exception").
  - `rebuild_catalogs()` → both catalog directories.
  - `publish_video(car_id)` → existing `/video` publish step.
  - `publish_site(car_id)` → existing `/site` publish step, including a
    delayed (>=60s) confirmation check if the live system supports it; if
    the delayed check fails, treat the whole publish step as failed so the
    controller can roll back / retry (this is the exact class of bug
    reported for UA-0010: a page that looked "updated" at write time but
    never actually finished rebuilding for the public HTTP endpoint).

## 6. Cross-cutting invariant

Every generator and the publisher must call `eta_engine.resolve_eta(...)`
and never read `days_to_kyiv` / `eta_manual` directly and independently in
multiple places — that duplication is the most likely root cause of the two
fields going out of sync across "page footer" vs "description" vs
"catalog" in the live system. Centralizing through one resolver function is
what makes the fix apply to *all* current and future cards without an ID
list.
