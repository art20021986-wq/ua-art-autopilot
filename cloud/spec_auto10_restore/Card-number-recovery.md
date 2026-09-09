# Stable card numbers after deletion

Contract: `UA-ART-SPEC-AUTO-10-RESTORE-001`, bounded candidate change only.

The captured production `cars_schema.next_auto_number` returns the suffix of
the last remaining CRM row plus one. An actual-source reproduction with rows
UA-0017 / UA-0018 followed by deleting UA-0018 returns UA-0018 again. That is
incompatible with the restored lifecycle's retired-identifier guard and could
attach a new vehicle to an old card URL or specification identity.

The candidate reserves each new identifier in a persistent SQLite sequence.
The reservation and the new card INSERT share the actual `db.create_card`
transaction. It does not commit callers' existing edits. Concurrent threads and
processes serialize using SQLite's write transaction; a busy or stale reader
fails instead of inventing an identifier. Failed, rolled-back creations may
reuse their uncommitted number; numbers in committed reservations are retained
after any later card deletion.

`ai_filter.store` and the explicit recognition-save handler formerly assigned
the number in a second transaction. All three captured assignment sites now
keep the number created by `db.create_card`, or atomically fill a legacy blank
number. Existing numbers and client-card creation are preserved. The existing
specification worker's scan remains responsible for automatically discovering
new / changed VIN input; this allocator does not make network requests.

## Candidate files and review boundary

Apply all three pure, hash-pinned patches from `allocator_integration.py`:

| Production source | Transformation |
| --- | --- |
| `cars_schema.py` | `patch_cars_schema`: replace reviewed `next_auto_number` |
| `db.py` | `patch_db`: reserve UID inside reviewed `create_card` INSERT transaction |
| `ai_filter.py` | `patch_ai_filter`: replace three reviewed number-assignment sites |
| New `car_number_allocator.py` | Copy runtime helper; no application imports or own connection |

These are four coordinated candidate files. The previously verified ten-module
v7 server package does **not** include this change. Its manifest and server result
must not be reused as proof for these new files. The combined candidate needs
source/runtime hash review, isolated actual publisher create/delete/create
verification, and the existing release gates before installation.

Only the new sequence table is added on the first successful reservation. No
existing card values are migrated, no tables are dropped, and no per-card
specification, media, publication state, or site shell is edited by this helper.
Database backups/rollback must preserve this sequence along with the CRM and
lifecycle archive; rolling only the sequence backwards is unsafe.

## Historical limits and entrypoint assumptions

Initial high water is the maximum of current card suffixes, the SQLite
AUTOINCREMENT history for cars, `ua_spec_lifecycle_archive.auto_number`, and
`media.auto_number` when present. Existing saved history is read within the
reservation's write transaction. A custom high suffix deleted **before** this
feature, with no surviving card, archive, or media record, cannot be recovered
from a smaller numeric row id. That historical absence must not be reported as
proof that the old number never existed.

The actual recognition callers supply `ai_filter.clean` output; its captured
`ALLOWED` fields exclude `auto_number`. Direct calls to `store(data)` with an
unreviewed dict remain a trusted-input boundary: this patch does not rewrite the
whole recognition field policy. Manually forcing a used number through an
unreviewed writer, or deleting/resetting the sequence table, is outside the
allocator's guarantee. The release must bind the reviewed runtime, audit other
writers, and retain the existing duplicate/retired UID publication guards.

## Focused verification

`tests/test_car_number_allocator.py` runs the runtime helper on isolated SQLite
databases. Actual source tests execute the exact reviewed function/class AST
nodes from captured sources with temporary paths; full CRM module top-level
imports and `/home/Carix` code are never executed.

Coverage includes the old highest-deletion defect, committed reservation
retention, deletion of all cards, out-of-order and archived suffixes, caller
transaction rollback and failure semantics, busy/stale readers, separate
processes and threads, the actual native CRM connection class and wizard create
function, and actual recognition `store` create/delete/create and concurrency.
These are isolated source/SQLite tests; they do not establish live publication.

Supply these external source paths to include actual-source tests:

```sh
UA_ART_ALLOCATOR_SCHEMA=/path/to/captured/cars_schema.py \
UA_ART_ALLOCATOR_DB=/path/to/captured/db.py \
UA_ART_ALLOCATOR_AI_FILTER=/path/to/captured/ai_filter.py \
python -m unittest discover -s cloud/spec_auto10_restore/tests \
  -p test_car_number_allocator.py -v
```

Exact input/candidate hashes, counts, and measured results are recorded in
`evidence/card-number-recovery.json` and `evidence/card-number-tests.log`.

## Фактический серверный результат

09.09.2026, запуск 08:23:43 UTC: **26/26 PASS на Python 3.10.12**, без ошибок и пропусков, 6.6821 секунды. Три защищённых дочерних процесса; запрещённых чтений, записей, сетевых действий и процессов — 0. Три рабочих исходника сохранили байты и метаданные. [Полученный с сервера JSON](evidence/allocator-server-result.json). Это изолированная проверка нумерации, не публикация карточек и не общий Gate B.
