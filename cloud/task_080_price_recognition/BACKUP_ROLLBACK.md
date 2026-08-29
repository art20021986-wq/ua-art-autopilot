# TASK 080 — backup and rollback controls

## Backup set

- `/home/Carix/cars_ui.py`
- `/home/Carix/local_ocr.py`
- `/home/Carix/ai_fast_schema.py`
- `/home/Carix/ai_filter.py`
- `/home/Carix/db.py` (audited dependency; not changed)
- consistent SQLite backup of `/home/Carix/crm.db`

Each backup must use a task/timestamp-specific directory, retain original mode,
and have SHA-256 plus size recorded before installation. The target directory
must be explicit; no broad recursive or unresolved path is allowed.

## Automatic stop/rollback conditions

- live hash drift or duplicate active definition;
- staging/test/compile failure;
- installed hash/read-back mismatch;
- process fails to become healthy after one reload;
- card count/identity/price/history/audit or database integrity deviation;
- any unrelated media, publication, status, description, VIN, ETA, or
  container change.

Rollback restores only the backed-up source files using atomic replacement,
compiles them, reloads the same process once, and performs a GET/read-only
postcheck. The database backup is evidence and an emergency recovery asset; it
is not restored automatically without proof and separate review of a data
mutation.
