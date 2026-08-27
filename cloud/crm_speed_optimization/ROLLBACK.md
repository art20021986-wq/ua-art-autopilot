# ROLLBACK — CRM-SPEED-001

No production or CRM change has been made by any cloud/ task in this
series, including this round. There is nothing to roll back yet.

If Gate A is ever executed by the owner/controller on PythonAnywhere, it
only writes inside `/home/Carix/qa/crm_speed_task020/<run_id>/`. Rollback
for that case is simply deleting the specific run directory; production
sources, `crm.db`, and the site/public trees are never touched by Gate A.

The existing safety backup remains the rollback point for any future,
separately approved Gate B installation:

- `/home/Carix/backups/crm_speed_20260827_1038_crm.db`
- `/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz`
- archive SHA-256: `b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913`

Gate B, if ever authorized, must re-verify this archive's hash before any
install action and must retain a documented one-command restore path.
