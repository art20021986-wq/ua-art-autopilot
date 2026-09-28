# Deletion writer integration candidate

Status: **NOT_READY_FOR_PRODUCTION**. This directory provides an offline,
hash-bound candidate and tests. It does not install files, migrate SQLite,
restart processes, delete media, or prove complete live-writer coverage.

## Contents

- `ua_delete_public_guard.py`: read-only final-write guard for `/home/Carix/video`
  and `/home/Carix/site`. Every `ua_delete_intents` state reserves car code,
  numeric identity, and normalized VIN. Missing migration fails closed. HTML
  and exact `sitemap.xml` payloads are checked before their final replacement.
  Historical UA-0002 has a separate immutable code/ID/VIN-hash reservation bound
  to the real completed emergency plan and receipt; no routine intent is invented.
- `build_writer_patch.py`: `transform(filename, original_bytes)` returns source
  only when the complete original SHA-256 equals the reviewed baseline.
  Existing script entrypoints execute after the appended wrappers.
- `test_writer_guard.py` and `test_publication_worker.py`: 36 tests with the actual existing publication fence,
  including contention, reentrancy, stale payloads, preserved media references,
  normal hide rollback, exact spec lock ordering, actual transformed urgent
  publication and stage reconciliation, worker admission and raw full-row CAS,
  concurrent sale/hide, late deletion rollback, historical evidence binding,
  delayed diagnostic cleanup/download/move, sitemap XML, and Telegram send failure.
- `cars_publication_patch.py`: exact publication-block transformation which can
  compose after independently approved list and deletion callback patches.
- `offline_validation.json`: compile/hash evidence without private source text.

The baseline hashes were independently rechecked by the parent executor against
live PythonAnywhere at 2026-09-21 05:52 UTC. This agent only used local sources.

## Exact integration points

| File | Hook | Protection |
| --- | --- | --- |
| `publikaciya.py` | final `_zapisat_atomarno`; `opublikovat`; `_otkat`; `ua0009_urgent_publish` | Guard final payloads/admission and legacy restore; urgent direct restore uses current-invocation CAS |
| `yadro.py` | final `zapisat_atomarno`; `_ua068_ensure_diag_files` | Guard payload replacement and missing diagnostic creation |
| `stranica.py` | final `zapisat`; `_ua068_ensure_diag_files`; `_v135` restore loop | Guard all resolved stems/aliases before writes and stale fallback restores |
| `publish_transaction_guard.py` | `_atomic`; `Snapshot.restore` | Guard public final writes; preflight all retained restore payloads before first unlink |
| `ua_spec_permanent.py` | `write_lock` | Acquire publication registry before spec lock |
| `ua_spec84_runtime.py` | replace `_writer_guard`; wrap `_atomic_existing` | Replace raw publication flock at its original order position with shared registry; retain other lock inodes and page CAS |
| `ua_additional_spec.py` | audit only | No public file writes. Metadata mutators remain unchanged, avoiding new synchronous CRM lock waits |
| `ua_stage_catalog_sync.py` | existing `reconcile` | No source patch: all commits already use guarded `pub._atomic` under publisher lock; conditional rollback retained |
| `cars_ui.py` | final `toggle_publish`; `_ua083_restore_publish_preimage` | Admission, publication and conditional DB rollback in one synchronous worker; Telegram awaits outside lease |
| `kadry_diagnostiki.py` | cleanup `os.remove`; download commit; two media relocation `os.replace` sites | Recheck current nonretired identity under publication fence immediately before final mutation; retain retired/absent target media bytes |

The two spec patches are an inseparable pair. Never install the permanent-lock
wrapper while an old spec runtime can call its raw publication flock. All
relevant workers must be quiesced, patched, and restarted together through the
approved installation coordinator. The exact full runtime is now reviewed; its
order remains task082 repair → task082 stage guard → task083 dedup → publication
registry → CRM lock → spec lock. The registry is entered in its original slot.
Do not call an `asyncio.to_thread` child
while its parent thread owns the publication fence; the child cannot inherit a
reentrant lease across thread boundaries.

Ordinary final HTML checks are deletion-specific. Current unpublished rows are
allowed when there is no tombstone, preserving the existing hide/rollback
sequence. Publication admission and spec/diagnostic writes separately require a
current published identity. Backups and media stay with their existing owners.
Diagnostic network downloads and temporary-byte preparation remain outside the
fence. Only final replacement, relocation and cleanup are guarded. Normal
current-car refresh still runs. A retired target may leave a newly prepared
temporary download or empty `neverno` directory; it cannot overwrite or relocate
the existing retained media. These final-mutation hooks were independently
reviewed with no remaining blocking finding.

The build must call `verify_historical_evidence(plan_bytes, receipt_bytes)` from
`ua_delete_public_guard` using the exact emergency plan and completed console
receipt. It verifies SHA-256 and target/audit/completion fields. Only reservation
metadata and evidence hashes belong in the distributable package.

## Remaining gates

1. Recheck the current writer/task inventory before installing. The authenticated
   2026-09-21 06:28 UTC inventory contains SEO task 1502215 in exact `--dry-run`
   mode, task 1505035 executing `mkdir` only, and disabled task 1502679. Exact
   SEO source SHA-256 `88922c6774bec9ea624b381f06f76167f768b2ffe57ad302f2e0fb5f3697d6f3`
   confirms dry-run writes only private receipt/locks, with no public commit.
   The enabled monitor writes evidence only. Dynamic WSGI sitemap filtering is
   covered by the separate route patch. Other SEO install/rollback modes and
   arbitrary manual scripts are outside this active inventory; they need review
   before future use. Stage synchronization uses guarded publisher writes.
2. Existing `rollback_backup` can replay an old broad snapshot without a current
   CAS preimage. The deletion coordinator must not call it. Use deletion-owned
   exact paths and compare current bytes before rollback. This candidate does
   not disable the unrelated legacy API.
3. Run composed integration/rollback checks and prove old processes have
   exited. Hash/compile success and isolated tests are insufficient for
   production PASS. The mapped current catalog generators emit literal page
   links and explicit vehicle attributes covered by this guard; arbitrary
   dynamic JavaScript payloads are outside that audited generator coverage.

Composition API:

```python
from build_writer_patch import apply_cars_ui_to_candidate
composed = apply_cars_ui_to_candidate(list_then_bot_candidate_bytes)
```

The first composition step must bind the entire current `cars_ui.py` baseline.
This worker step additionally binds its unchanged publication region to
`558db6d61e7976cb34f7a0054c27cb9dda76c300cce50449cbba556108f963ec`.
The existing publication routine remains synchronous within one worker; no
worker lease is inherited across threads. Initial publication compares the raw
full row within `BEGIN IMMEDIATE`; failed publication restores only its
`published` field if the raw full row still exactly matches its captured own
postimage. Any newer operator edit refuses rollback, including sale/unpublication
with the same published value. Old restore calls without a
current invocation's expected write are read-only checks. Telegram failure
following successful commit no longer initiates a stale DB rollback.

Test invocation (the file must be the reviewed existing fence):

```sh
UA_TEST_FENCE_SOURCE=/path/to/publication_fence.py \
UA_TEST_PUBLISH_SOURCE=/path/to/publikaciya.py \
UA_TEST_SPEC_SOURCE=/path/to/ua_spec84_runtime.py \
UA_TEST_STAGE_SOURCE=/path/to/ua_stage_catalog_sync.py \
UA_TEST_CARS_SOURCE=/path/to/cars_ui.py \
UA_TEST_KADRY_SOURCE=/path/to/kadry_diagnostiki.py \
UA_TEST_PRIVATE_ROOT=/path/to/verified_private_sources \
python -m unittest discover -s cloud/crm_delete_recovery_002/writer_patch -p 'test_*.py' -v
```

Independent read-only review found no definite flaw in the mapped HTML commit
points and confirmed the raw-flock skip addresses the identified self-deadlock.
The urgent direct-copy bypass found by a second reviewer is now patched and
regression-tested; that reviewer confirmed the fix. The current scheduled
sitemap dry-run was independently reviewed and cannot write public payloads.
Old durable shared-page CAS restrictions remain. Full-source spec lock-order
inspection and tests are complete. These are offline results; installation,
old-process exit and composed live checks remain release gates.
