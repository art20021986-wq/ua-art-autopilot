# CRM-SPEED-001 rollback notes

## Current state

Nothing in this package has been installed into production. No file under `/home/Carix` outside `/home/Carix/qa/crm_speed_task020/` is ever written by this package. Therefore there is nothing to roll back in production as a result of this task.

## Rolling back a Gate A run

A Gate A run only creates a new timestamped directory under `/home/Carix/qa/crm_speed_task020/<run_id>/` containing snapshot copies, candidate copies, diffs, `receipt.json`, and `REPORT.md`. To remove the evidence of a run, delete that specific run directory. This has no effect on production because production was never written.

## If a future Gate B installation is separately approved

This package does not perform Gate B. If the owner later approves installing a specific candidate file into production, the pre-existing safety backups referenced in the incident evidence remain the rollback basis for that separate, future action:

- `/home/Carix/backups/crm_speed_20260827_1038_crm.db`
- `/home/Carix/backups/crm_speed_20260827_1038_before.tar.gz`
- archive SHA-256: `b6e68a8382e5a6bbf0e7ffc957ac33d14c53db28b89a08cfd6e456e15a5a8913`

Any Gate B rollback plan must be written and approved at the time Gate B is authorized. This document does not authorize Gate B.
