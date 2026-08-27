# ROLLBACK — CRM-SPEED-001 Gate A (round 2)

Gate A performs no production writes, so there is nothing to roll back
from running it. Rollback only becomes relevant after a future, separate
Gate B installation step — which this package does not perform.

## If a future Gate B installation is ever authorized

1. Stop before installing if any Gate A evidence entry is not `passed:
   true`.
2. Keep the verified backup as the rollback source:
   - `/home/Carix/backups/crm_speed_20260827_1038_crm.db`
   - `/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz`
   - SHA-256: `b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913`
3. Restore by extracting the tarball over the original paths and
   replacing `crm.db` with the backed-up copy, only after stopping any
   process that has the database open.
4. Re-run Gate A's fingerprinting against the restored tree to confirm
   it matches the pre-change fingerprints recorded in the corresponding
   receipt.

This document remains a placeholder for the eventual Gate B rollback
procedure; Gate A itself requires no rollback action.
