# UA0022 forward reconciliation candidate v2

Corrected data-only candidate built from exact immutable main bytes. It atomically reads and hash-binds the input manifest, validates the source commit/path/blob/SHA provenance of the observed installation receipt and fresh health evidence, requires an exact route-to-final-URL map, derives later public byte changes, archives the exact HALT bytes, and emits a receipt that satisfies the active canonical receipt contract using explicitly scoped evidence. No runtime, CRM, site, Preview, reload, publication, rollback, main or HALT write was performed during preparation.

Status: READY_FOR_INDEPENDENT_REVIEW_NOT_EXECUTED.
