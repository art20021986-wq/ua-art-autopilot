# TASK 079 — Gate B Manual Workflow (PREPARED, NOT EXECUTED)

Contract: `CRM-CONTAINER-STAGE-SYNC-004 v1.0`

MEMORY MARKERS (verbatim):
`CONTEXT_BUNDLE_SHA256=2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c`
`MEMORY_VERSION_READ=4`

This document is a **plan only**. Nothing in this document has been executed.
No step below has been run against production, CRM, or PythonAnywhere. Gate B
execution remains forbidden for this task per the contract.

## Exact single owner approval token

Gate B may only begin after the owner supplies, through the normal
ChatGPT/Codex-relayed channel, the exact distinct token:

```
CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED
```

Merely mentioning this token in any documentation, report, or chat message is
**never** approval. Approval requires the owner to explicitly issue this
token as an instruction to proceed, through the durable GitHub handoff
described in the repository's top-level protocol.

## Preconditions before Gate B may even be scheduled

1. A separate, evidence-backed Gate A capture step must supply the real
   byte content of `db.py`, `cars_ui.py`, `konteyner.py`, `stranica.py`, and
   `publikaciya.py`, each verified against the SHA-256 anchors already
   proven in TASK 076/077 evidence.
2. That same step must capture the exact active source of
   `konteyner.prinyat`, `konteyner.sprosit_dni`, `konteyner._peresobrat`,
   `cars_ui.apply_value`, and `cars_ui.toggle_publish`, recorded the same
   evidentiary way as the full-file anchors, and populate
   `live_patcher.GOLDEN_FUNCTION_SOURCE` from that capture.
3. `live_patcher.apply()` must then be re-run and must produce a real
   candidate patch file (not raise `FailClosedError`) for every target file.
4. The candidate patch must be re-verified against the full sandbox test
   suite plus a CANARY run against a true copy of the CRM before any
   production path is even staged.
5. A fresh, current full-file BACKUP of all five live files must be taken
   immediately before any production write, timestamped and stored under
   `cloud/`.

## Planned Gate B steps (to be executed only after all preconditions above
and explicit owner token approval)

1. Re-confirm BACKUP freshness and re-verify all five SHA-256 anchors
   against the current live files immediately before write.
2. Apply the verified `live_patcher` candidate patch to `konteyner.py` and
   `cars_ui.py` only, replacing the two write call sites with calls to the
   shared `eta_release_candidate.run_eta_sync_release` writer.
3. For UA-0009: run the shared writer with N=30, no forced status change,
   and apply `sanitize_stale_arrival_sentence` to its description with
   `must_contain_fragment="9 вересня 2026"` only.
4. For UA-0010 and UA-0011: run the shared writer with N=30, no forced
   status change beyond the exact approved ferry-to-`sea_loaded`
   normalization if and only if their current status is on the TASK 077
   approved ferry list.
5. For UA-0012: run the shared writer with N=30 and the same approved
   ferry normalization, plus ensure the diagnostic page or an explicit
   placeholder exists.
6. After each car, perform independent read-back, bounded staged-file
   install, and publisher verification exactly as implemented in
   `run_eta_sync_release`. On any failure, execute the compensating
   rollback and stop — do not proceed to the next car.
7. Record a full post-write evidence capture (hashes, DB row read-back,
   rendered public pages) equivalent in rigor to the TASK 076/077 Gate A
   evidence, before considering the release complete.
8. Report the outcome back through the normal `cloud/latest_status.md` and
   `cloud/owner_reply.md` channel. Do not perform any process reload beyond
   what the existing safe publisher already does as part of verified
   publication.

## Explicit non-actions

- No step above has been executed.
- No production, CRM, or site path has been touched by this task.
- No process reload has been performed or requested.
- This plan does not itself constitute or request approval.
