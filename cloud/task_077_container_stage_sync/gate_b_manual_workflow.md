# Gate B — prepared manual production workflow (NOT EXECUTED)

Contract: `CRM-CONTAINER-STAGE-SYNC-004 v1.0`

Exact separate owner token:

```
CRM-CONTAINER-STAGE-SYNC-004-V1.0-PRODUCTION-APPROVED
```

The token printed in this document is not approval. Gate B is blocked until
the owner sends that exact text as a new command after Gate A PASS.

## Preconditions

1. Repository Gate A for the exact candidate commit is
   `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`.
2. Fresh GET confirms all five full-file SHA-256 and eight function SHA-256
   anchors recorded in `live_patcher.PATCH_SPECS`.
3. A DB backup including optional WAL and byte backups of both primary pages,
   both diagnostic pages and both shared catalogs are stored outside
   `/home/Carix`.
4. The exact token above, explicit `apply=True`, and that external empty
   backup directory are supplied together.

## Bounded installation

From a reviewed controller checkout:

```python
from live_patcher import apply_patch_bundle
result = apply_patch_bundle(
    root="/home/Carix",
    backup_dir="/home/task077-backups/<UTC-unique-id>",
    owner_token="<exact owner command>",
    apply=True,
)
```

The installer:

- verifies the five whole-file hashes before any write;
- selects exactly one audited definition for each of eight source hashes;
- builds and compiles every patched source in memory;
- backs up every target outside the live root;
- atomically installs the shared guard, TASK 076 ETA engine and five patched
  source files;
- restores exact source preimages automatically on any install/compile error.

## Existing-card correction and verification

After installation, call the one shared `apply_eta_days_live` entry point
sequentially for integer IDs 9, 10 and 11 with N=30. TASK 077's separately
approved UA-0012 legacy migration may then use the same entry point; its
`sea_transit` status can only move forward to `sea_loaded`.

Each call must prove before returning success:

- DB pair exactly `days_to_kyiv=30`, `eta_manual=2026-09-28`;
- canonical ferry status `sea_loaded` where allowed;
- UA-0009 stale arrival sentence removed while unrelated dates remain;
- primary + diagnostic/placeholder in /video and /site;
- both shared catalogs;
- local byte read-back and public /video + /site read-back;
- exact preimage value of `published`.

Any failure removes only this operation's audit IDs and restores the exact DB
row and six file bytes. If any card in the production batch fails, the
controller restores the full pre-Gate-B backup and stops with one failure
message. No automatic second production attempt is allowed.

## Final postcheck

Re-fetch DB, five live sources, UA-0009/0010/0011 pages and both catalogs.
Record hashes, Gate B result and rollback status in sanitized evidence. Only a
complete postcheck PASS permits the owner-facing statement that production is
fixed.

Current state: Gate B not run; production writes = 0.

