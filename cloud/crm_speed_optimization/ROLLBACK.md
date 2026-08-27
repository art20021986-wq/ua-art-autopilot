# ROLLBACK.md — CRM-SPEED-001 (Task 024 correction)

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4

## Current state

No production file, database, bot process, site, or media tree has been
modified by this package. Everything Gate A writes lives beneath
`/home/Carix/qa/crm_speed_task020/`. There is nothing in production to
roll back as a result of this task.

## If Gate A is ever run and its QA artifacts need to be removed

```
rm -rf /home/Carix/qa/crm_speed_task020/<run_id>
```

This only removes the isolated QA copy; it cannot affect production
because Gate A never writes outside that directory.

## If a future Gate B installation is ever authorized and needs reverting

Use the existing, already-verified safety backup referenced in the task
contract:

* `/home/Carix/backups/crm_speed_20260827_1038_crm.db`
* `/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz`
  (SHA-256 `b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913`)

Gate A's own `receipt.json` in the relevant run directory records the
exact before/after fingerprints of every protected file it inspected, so
any future Gate B reviewer can confirm restoration correctness against
those recorded hashes. Restoring the archive and database backup, if ever
needed, is an owner-approved manual production action outside the scope
of this Cloud package.
