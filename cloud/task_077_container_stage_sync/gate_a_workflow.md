# Gate A — GET-only live audit workflow (to be executed by controller with read creds)

Mode: BACKUP already assumed done under TASK 076 lineage. This workflow performs **GET only**.
Any non-GET call is a hard stop.

## Preconditions

1. TASK 076 Gate B result has been read and understood; this task extends, not replaces,
   its ETA transaction.
2. Controller has read-only credentials sufficient to GET current source files and DB copy
   (or a GET-exposed read replica) from PythonAnywhere.
3. `PRODUCTION_WRITE=NO` enforced by tooling; `gate_a_audit.py` hard-refuses any verb other
   than GET, and refuses any SQLite `INSERT/UPDATE/DELETE/PRAGMA writable_schema`.

## Steps

1. Run `python3 gate_a_audit.py --target cars_ui.py --sha` (repeat for `konteyner.py`,
   `cars_schema.py`, `db.py`, active ETA writer file, publisher/generator files).
2. Run `python3 gate_a_audit.py --count-callbacks sea_loaded,sea_transit,sold_transit
   --files cars_ui.py,konteyner.py` — record counts per active handler chain only; skip
   any file confirmed to be an archive/backup/dead code path.
3. Fetch `crm.db` (+ optional WAL) as GET/read-only copy; do not open in read-write mode.
4. Fetch the two live catalog pages and both card pages for UA-0012 and UA-0009.
5. Record all SHA256 + counts + handler order into `evidence/gate_a_findings.md`.
6. Determine active handler order (which registered callback for `sea_loaded` actually wins
   if duplicate registrations exist). Do not patch anything found here — audit only.
7. Final verdict line must be exactly one of:
   - `GATE_A_RESULT: PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`
   - `GATE_A_RESULT: FAIL <reason>`

## Hard stops

- Any POST/PUT/DELETE attempt anywhere in this workflow is forbidden and must abort.
- Any DB write attempt is forbidden and must abort.
- Do not touch Gate B of TASK 076; do not spawn a second ETA writer.
