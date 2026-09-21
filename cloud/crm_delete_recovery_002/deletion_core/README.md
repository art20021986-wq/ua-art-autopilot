# CRM deletion coordinator — installation candidate

This package contains new coordinator/runtime code and the previously reviewed
transactional core. **It is not installed and is not a production PASS.**
Private captured source, CRM rows, credentials and public fixture copies are
not included in this directory.

## Stable bot API

Deploy this directory's runtime modules as `ua_crm_deletion_core/`, with a
top-level `ua_delete_runtime.py` facade exporting
`ua_crm_deletion_core.runtime.create_coordinator`.

```python
worker = create_coordinator(db=existing_db_module)
token = worker.confirm(car_id=actual_id, actor_id=staff_id)
display = worker.confirmation(token=token, actor_id=staff_id)
intent = worker.admit(token=token, actor_id=staff_id)
receipt = worker.resume(operation_id=intent['operation_id'])
unfinished = worker.pending()
```

All operations are synchronous. The Telegram adapter must run them off the
event loop and preserve staff checks. A numeric legacy confirmation is not a
valid token. The display method returns only identity/version metadata, not
the complete saved CRM row. `resume()` is a trusted worker/startup entry.

`admit()` returns a durable intent; it does not mean deletion is complete.
Only a `COMPLETE` receipt permits the completion message. A duplicate terminal
operation returns its original committed receipt after rejecting a replacement
CRM identity. It does not claim a new HTTP check or replay historical pages.

## Durable behavior

1. Authorize staff and bind confirmation to actual ID, code, VIN and typed
   full-row snapshot. A later target edit invalidates the confirmation.
2. Under the existing publication fence, create a coherent SQLite backup,
   run integrity/schema/full-target-snapshot checks and read back exact file
   backup checksums. Persist immutable before/after images and their manifest.
3. Commit original row snapshot, deletion intent and pending job together,
   setting only `published=0`. Every intent state permanently reserves identity.
4. Retire exact shared HTML spans and sitemap entries, then direct aliases.
   Every effect compares current bytes first. No media path is a write target.
5. Observe real HTTP outside all publication/database locks. Require 404/410
   without redirects for exact served targets; shared served files require
   200 and exact current after-image hashes. Explicitly unserved mirror files
   are checked locally. Public deletion cannot classify every target local-only.
6. Recheck local state under the fence, delete only the unchanged admitted
   CRM row, commit its job state, and obtain a second HTTP observation before
   committing completion. Recovery never restores a database or sold listing.

If another legitimate publication changes shared pages during the operation,
the coordinator captures the latest pages under the same fence, removes only
the target, obtains a new verified backup and commits a bound rebase checkpoint.
The original intent/backup, exact route plan and media hashes remain authoritative.
New direct-page contents are never accepted by rebasing. Up to three attempts
handle a race during HTTP checks; sustained changes leave the original job
pending. Repeated restarts use the same operation and current checkpoint.

The original `REQUESTED` intent plus job can finish after legacy row loss; no
new row or fabricated intent is inserted. A historical deletion such as the
already-absent UA-0002 without a routine intent requires its separately reviewed
incident reservation. This package does not rerun the emergency deletion.

## Concrete runtime binding

`runtime.create_coordinator(db=...)` reads only
`/home/Carix/ua_crm_deletion_state/runtime.json`. The directory must exist with
mode 0700. Factory/import never migrates, writes config, restarts a process or
enables a bot handler. `install_reviewed_schema()` is a separate installer-only
entry after that installer has verified its full backup.

Runtime config has exactly these fields:

| Field | Meaning |
| --- | --- |
| `version` | `1` |
| `application_schema_sha256` | Reviewed live application DDL digest excluding SQLite internals and deletion tables |
| `source_sha256` | Exact installed source pins, including `db.py`, `publication_fence.py`, `ua_site_counters.py` |
| `shared` | Exact relative surface → `CATALOG`, `MODERN_HOME`, `LEGACY_HOME` or `SITEMAP` |
| `shared_routes` | Every shared surface → exact served URL list, or `[]` for a verified unserved mirror |
| `direct_route_prefixes` | Explicit URL prefixes for both `video` and `site`; `video` cannot be empty |
| `writers_receipt_sha256` | Reference to independently accepted complete writer-integration receipt; the installer owns its verification |

The observed 21 September application schema digest is
`1d5aacc240cc0e330ae059bf56e32a3ce50200ee1bfe08da8834ae4f98c0480a`.
The current schema has no triggers on `cars` or incoming foreign keys; its four
media triggers remain unchanged. The core still rechecks schema on every
transaction. A changed schema requires review, not relabeling the old digest.

The binding uses actual `db.connect()` (`Soedinenie`, an SQLite Connection
subclass), current active staff records and the installed publication fence.
Its counter module is source-pinned. `patch_home` is cloned into isolated
globals where `inject_script` is an identity function, preserving all existing
scripts; the imported module itself is unchanged. Catalog membership and stage
counts are re-read from both current mirrors.

## Validation and remaining integration

The normal suite covers SQLite state, public guards and real localhost HTTP
end-to-end deletion, interruptions, corrupt backups, expired/redirected HTTP,
operator edits, rebase/resume, direct replacement refusal, unrelated data and
media preservation, callback identity and HTML/XML source-span preservation.

`test_runtime_current.py` additionally requires environment paths to the private
captured source and public fixtures. It executes the exact current DDL in a
temporary DB and the source-selected current `Soedinenie` connection functions,
then runs the concrete binding with the actual counters module and captured
page markup. No production source module is imported or connected. Its HTTP
observer is a local fixture; real HTTP is separately exercised by the ordinary
coordinator tests. These source-bound tests skip when inputs are unavailable.

Remaining release gates: independently reviewed complete writer/restore/media
and creation coverage; exact installation source/hash binding and fresh backup;
real route inventory (including dynamic endpoints handled outside static-file
hash checks); true 404/410 route integration; schema installation; correct CRM
restart; live Telegram deletion/resume and public acceptance. New files alone
do not establish those facts.
