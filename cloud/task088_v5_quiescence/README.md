# PR114 quiescence protocol: isolated prototype

This folder prepares a remedy for a demonstrated installation race. It does
not change the existing installation/runtime package, call PythonAnywhere,
authorize a pause, produce a writer PASS, or close a completion criterion.
All test observations are explicitly synthetic fixtures. The prototype's
`PROTOTYPE_INSTALL_BOUNDARY_ONLY` is not a canonical installation permit.

## Why the current release is blocked

Hash-matched current `cars_ui.py` has an active callback
`photo_remove_all -> _ubrat_fayly_foto -> os.remove` before its DB update.
Diagnostic/video removal also has filesystem work after DB commit; the legacy
`stranica.main` rollback can write HTML outside the publication lock. SQLite
`BEGIN IMMEDIATE` and the existing publication flock cannot exclude these
filesystem effects. An after-image with new locks does not fence an already
running predecessor during its own installation.

Evidence is preserved in
`cloud/task088_v5_acceptance/resume_20260915_2/WRITER_FENCE_INDEPENDENT_REVIEW.json`.
The real specification-worker and monitor closure must also be reviewed. The
existence of `analitika_stop.txt` does not prove every WSGI worker is drained.
An empty process list observed from a different execution context is not proof
that the CRM process or its children are absent.

## Authorization provenance and boundary

The attached UA-ART-PR114-COMPLETION-004 requires actual conflicting-writer
exclusion (criterion 11), isolation of failure experiments, preservation of
newer operator data, and continuation through the existing canonical gates.
Its section 7 says: “Рабочую систему ради моделирования отказа не останавливать.”
It does not state an absolute ban on a planned installation pause or restart.
Its preservation and no-gate-weakening requirements remain controlling.

The historical `TASK088-GE-PRICE-CRM-STAGE2-INSTALL` request expressly prohibited
a bot restart for that historical child. It is not reused for this release.
`cloud/task088_price_sync/INSTALLER_CONTRACT.md` explicitly places a restart of
the positively identified CRM process after the actual install. The current
v5 controller additionally requires supervisor 266084, exact command
`python3.10 /home/Carix/start_safe.py`, enabled and Running before and after
each individual child. Its README states that this child never restarts CRM.

Therefore stopping CRM under the current, unchanged controller is invalid.
A reviewed phase-aware replacement is required before any such operation.
There is no permission here to delete/recreate a service, change its command,
weaken HALT/locks/Gate, use an old launch, or claim that disabled equals drained.

The parent verified the provider's primary API documentation:
[PythonAnywhere API](https://help.pythonanywhere.com/pages/API/).
`always_on/{id}/` supports GET and PATCH of `enabled`; DELETE stops and deletes
the service and is excluded. Provider capabilities do not prove graceful child
drain or authorize their use. The prototype includes no API implementation.

## Smallest complete remediation design

1. Finish a current, authenticated inventory of all writers: CRM supervisor and
   descendants, specification work, other Always-On/scheduled processes,
   connection monitor and WSGI side effects. Classify each exact source version
   as controlled process, enforceably held lock, or proven read-only. Unknown
   writers block the plan. Preserve ID 266084 and its exact prior configuration.
2. Review a bounded canonical maintenance/quiescence scope before its first
   provider mutation. It must bind the final code, affected services, journal,
   observation method, restore protocol and existing owner authorization.
   Do not synthesize `VERIFIED` to satisfy the existing installation gate.
3. Persist a unique pause intent before PATCH. Read back exact ID/command and
   provider state, then independently prove complete process membership, zero
   active descendants and drained in-flight work. Provider `enabled=false`
   alone is insufficient. If drain cannot be proved, no backup/install starts.
4. Retain the confirmed quiescence across backup, canonical OPEN, installation,
   verification and reconciliation. Existing publication/SQLite locks remain.
   Refresh actual observations after lengthy backup; old timestamps and Gate
   hashes are immutable. The current fixed evidence binding needs a reviewed
   refresh protocol; this prototype does not change it.
5. Only admit the existing canonical installation after its real fresh gates
   and writer facts pass. Keep source/HTML CAS, full backup, schema checks and
   independent DB readback. A lost installation reply first requires current
   source/schema/DB/in-flight reconciliation under the same operation ID.
6. Restore `enabled=true` only after the complete old or complete new version
   is independently coherent. Never resume on a timer or restore an old DB
   over newer operator data. Re-read exact prior supervisor identity and
   configuration, one live instance and actual loaded code. This restores a
   service; it is not live price-synchronization acceptance.

The temporary quiescence is only the bootstrap remedy. Stage4 also needs a
permanent cooperative fence at all actual photo/video/diagnostic mutation and
complete rebuild/rollback boundaries, plus reviewed specification writers.
Preserve publication-before-SQLite ordering. A naive lock around an async
callback that awaits a thread acquiring the same flock can deadlock. Do not
patch only the visible photo callback or confuse `.ua_spec84_write.lock` with
the installer publication lock. A source change invalidates its code pins;
recheck only affected software/Preview evidence and retain unchanged visuals.

## What the prototype implements

`state_machine.py` contains no network calls, process signals, subprocesses,
production path writes, credential reader or live installer. It writes only
the caller-selected local journal. Each record is hash-chained and fsynced,
with an exclusive process lock. The reviewed plan is stored as immutable
canonical bytes; each transition checks its journal binding. Returned plans
and intents are detached copies. Truncated or altered history fails closed.

The transition states are NEW, PAUSE_PENDING/UNKNOWN, QUIESCED,
APPLY_PENDING/UNKNOWN, COHERENT_BEFORE/AFTER, RESUME_PENDING/UNKNOWN and
RESTORED_PENDING_LIVE_ACCEPTANCE. Unknown outcomes yield only a read-only
reconciliation intent, not a second PATCH or a new operation identity.
Before/after writer source pins are distinct and phase-bound.

Normalized observation fields are interfaces for a future evidence collector,
not authentication. In particular `membership_complete`, `READ_ONLY_PROVEN`,
coherence flags, source-set hashes and canonical admission must be derived
from real evidence by reviewed code. Merely setting them in JSON is invalid.
The production authorization hash in a prototype plan is not independently
verified here; existing canonical validators must still perform that work.

For partial multi-supervisor pause, the model remains PAUSE_PENDING/UNKNOWN
until a complete drain is proved. It deliberately has no automatic selective
retry or compensation. A production adapter must reconcile each provider
request to a proven terminal outcome and implement reviewed bounded recovery
before this model could be integrated. No recovery-complete claim is made.

## Verification and remaining integration work

Run the new isolated checks only:

```sh
python3 -I -B -m unittest discover -s cloud/task088_v5_quiescence -p test_state_machine.py -v
```

The tests cover loss of replies before/after journal durability, fsync failure,
competing writers, an active filesystem worker despite disabled provider state,
incomplete process visibility, unknown writers, lock loss, stale observation,
mixed installation, operator-data preservation, exact phase-specific code pins,
plan mutation, and restart reconciliation. See `VALIDATION.json` and its raw
stdout/stderr files for the final run and pinned source hashes.

Not implemented: real graceful drain, authenticated observation collector,
partial provider-action recovery, canonical maintenance authorization and
integration, long-backup evidence refresh, permanent filesystem fences,
reader credential provisioning, deployment, or Stage3/4 acceptance. The
existing 82-file package and all production controls remain unchanged.
