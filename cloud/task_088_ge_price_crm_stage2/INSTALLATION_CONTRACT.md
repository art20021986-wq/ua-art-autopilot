# Stage 2 installation and acceptance

The owner explicitly authorized urgent installation and said that he will check
the restored bot. Installation therefore has the child identity
`TASK088-GE-PRICE-CRM-STAGE2-INSTALL`. It never creates or substitutes the parent
`TASK088-GE-PRICE-CRM-STAGE2` acceptance receipt.

## Bound scope

The child uses the existing **CRITICAL production** route with a fresh account
storage measurement, ordinary Gate A/B, source hashes, online SQLite backup,
source rollback, unique nonce and exact runtime claim. No runtime policy,
production classification, Stage 1 storage exception or historical receipt is
changed. Only the approved `cars_ui.py` source is replaced. The database is read
and backed up; no live price, history, schema or audit change occurs during this
installation. No CRM or website process is restarted by this controller.

`FINISHED` for the child means only
`INSTALLATION_AND_SOURCE_DB_READONLY_VERIFY`. Its receipt explicitly records
`stage2_acceptance=PENDING_TELEGRAM_CHECKS`, `telegram_ui=NOT_PERFORMED`, pending
process activation verification and `stage3_allowed=false`. The legacy field
`crm_unchanged` refers to database schema and vehicle values; the approved UI
source replacement is separately and explicitly recorded in its scope.

The parent and obsolete R2 request now point to `acceptance_controller.py`, a
read-only fail-closed sentinel. They cannot rerun Stage 1 or repeat installation.
They remain blocked until the separate real Telegram acceptance implementation
and evidence exist. No parent PASS can be derived from child FINISHED.

## Finalization before a launch

The request, manifest, Gate A and approval bind the reviewed installation to
exact source hashes and time-limited account quota evidence. Null observations
and all-zero hashes never count as observations or approvals. Target checks
remain mandatory before source replacement.

1. Pin the full source/dependency hashes, remote Stage 1 receipt hash and approved
   candidate source hash in `deployment_plan`. Validate the actual schema during
   backup. Check CRM supervisor 266084 through authenticated API reads before
   and after each operation. Its command, enabled flag and Running state
   must match. This checks supervisor identity, with OS PID continuity explicitly
   unverified because PythonAnywhere console namespaces do not expose the CRM PID.
2. Save the current account quota observation as
   `state/storage/TASK088-GE-PRICE-CRM-STAGE2-INSTALL.json`. Its exact parsed JSON
   must match `deployment_plan.quota`; the request pins its file SHA-256. The
   measurement must be at most 30 minutes old and leave enough room for the real
   database backup. Do not reuse global filesystem capacity as account quota.
3. Pin every Python file in the deployment package, including its static fixture
   data, safe installer tests and parent acceptance sentinel. Dynamic local
   handler/connection fixtures live in the sibling
   `cloud/task_088_ge_price_crm_stage2_tests/` package and are never deployed or
   invoked by a production workflow. The normal production inspector remains
   unchanged. Add any new deployment modules to the exact package closure.
   Manifest `expected_after_sha256` and `deployment_plan.expected_candidate_sha256`
   must be the same real candidate hash. Record actual Gate A evidence.
   If `price_parser.py` is confirmed absent, record its exact path in
   `deployment_plan.expected_absent_dependency_paths` instead of inventing a
   source hash. The installer requires the file, package and any importable
   alternate module all to remain absent; otherwise it stops before mutation.
4. Use one fresh nonce both as `deployment_plan.nonce` and the owner's structured
   approval `launch_nonce`. Pin manifest and Gate A, compute the authorization
   subject hash with `automation.autostart_intake.request_authorization_sha256`,
   then pin the finished owner approval and final request. The existing owner
   authorization applies; no additional permission is required merely to fill
   the technical bindings after successful checks.
5. Preserve all old nonces, claims, launch records and receipts. No new receipt
   is pre-created. After the reviewed package reaches main, a **separate commit
   adding exactly one new AUTO launch JSON** triggers the existing route.

## Remote protocol

The controller uploads only hash-pinned `remote_installer.py`, `patcher.py`,
`runtime.py` and immutable operation plans into
`/home/Carix/autopilot_inbox/cloud/task_088_ge_price_crm_stage2/runs/<run_id>-<request_sha256>/`.
Each phase runs `remote_installer.py --operation backup|execute|verify|rollback
--plan <operation>-plan.json` as one newly created scoped AlwaysOn task. Only that
positively identified task is removed afterwards; existing CRM/monitor tasks
are untouched. Remote phases write their own `<operation>-result.json`, with
bindings for task, request, run, transaction, manifest, nonce and backup hash.
Any failed install/verification prevents a success receipt and leaves ordinary
production rollback handling enabled. Backup restores only the approved source;
it never overwrites newer unrelated database changes.

Full parent acceptance still requires the running bot, both actual menu entries,
supported numeric/currency-marked inputs, each commit followed by a fresh DB read,
market independence, exact original-value restoration and unrelated CRM checks.
