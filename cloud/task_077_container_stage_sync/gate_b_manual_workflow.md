# Gate B — prepared manual production workflow (NOT EXECUTED)

Contract: `CRM-CONTAINER-STAGE-SYNC-004 v1.0`

Exact separate owner token:

```
CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED
```

The owner issued the separate production command `Продакшн в работу.` after
Gate A PASS. The controller may supply the exact machine token only for that
single manual dispatch; the workflow has no push/schedule trigger.

## Preconditions

1. Repository Gate A for the exact production bundle is
   `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.
2. Fresh GET confirms all five full-file SHA-256 and eight function SHA-256
   anchors recorded in `live_patcher.PATCH_SPECS`.
3. A consistent SQLite backup and byte backups of seven source files, both
   primary pages, both diagnostic pages and both shared catalogs are stored in
   a collision-safe durable inbox directory outside the touched live paths.
4. The source installer additionally uses a unique transient backup outside
   `/home/Carix`; the exact token and explicit `apply=True` are supplied
   together.

## Bounded installation

The only production entry point is the manual GitHub workflow:

```text
.github/workflows/task077_container_stage_sync_gate_b.yml
```

The installer:

- verifies the five whole-file hashes before any write;
- selects exactly one audited definition for each of eight source hashes;
- builds and compiles every patched source in memory;
- creates the durable batch backup before the first live write;
- gives the source installer a unique external transient backup;
- atomically installs the shared guard, TASK 076 ETA engine and five patched
  source files;
- restores exact source preimages automatically on any install/compile error.

## Existing-card correction and verification

After installation, resolve `UA-0009`, `UA-0010` and `UA-0011` by their unique
`auto_number` in a fresh read-only query and require exactly one row for each.
Do **not** infer a database ID from the visible card number. The owner's newer
instruction moves UA-0011 back to Korea and clears its container/ETA, so TASK
077 must preserve that row byte-for-byte. Pass only the resolved UA-0009 and
UA-0010 integer IDs to `apply_eta_days_live`, sequentially, with N=30.

Each call must prove before returning success:

- UA-0009/UA-0010 DB pair exactly `days_to_kyiv=30`,
  `eta_manual=2026-09-28`;
- canonical ferry status `sea_loaded` where allowed;
- UA-0009 stale arrival sentence removed while unrelated dates remain;
- UA-0011 and every other CRM row remain identical to the fresh preimage;
- primary + diagnostic/placeholder in /video and /site;
- both shared catalogs;
- local byte read-back and public /video + /site read-back;
- exact preimage value of `published`.

Any failure removes only this operation's audit IDs and restores the exact DB
row and six file bytes. If either card in the production batch fails, the
controller restores the full pre-Gate-B backup and stops with one failure
message. No automatic second production attempt is allowed.

## Final postcheck

Re-fetch DB, seven installed live sources, UA-0009/0010 pages, the protected
UA-0011 row, diagnostics and both catalogs. Record hashes, Gate B result and
rollback status in sanitized evidence. Only a complete postcheck PASS permits
the owner-facing statement that production is fixed.

Current state: owner production command received; exact-bundle Gate A and
exclusive production dispatch are in progress.
