# Writer fence candidate after handoff 006

This is an isolated candidate, not an installed protection or publication gate.

The handoff review reproduced two defects: an inherited Condition could deadlock a forked child, and a changed lock inode could be granted after a wait. The candidate now registers fork cleanup, tracks descriptors through acquisition and release, closes child descriptors without unlocking the parent, and checks the lock path again before a grant, nested entry and ownership assertion.

The affected module suite passed 18 tests. Historical product suites 446/183/120 and historical Preview 24/24 were not rerun. Their retained results do not certify this changed module or a newly assembled release.

The unchanged test_publication_fence.py plus test_fork_regressions.py and test_inode_regressions.py reproduce the final module check from this directory:

    python3 -B -m unittest -v test_publication_fence test_fork_regressions test_inode_regressions

HANDOFF006_VALIDATION.json is the current version-bound index. Raw output, intermediate failures and the separately preserved fork-only candidate are under handoff006_evidence. Those earlier validation files retain their original relative source names: publication_fence.py refers to the fork-only source for the 4- and 15-test reports, and to the current parent source for the final 18-test report. No old test result is reassigned to new bytes.

## Integration still required

Obtain and privately retain the exact pinned cars_ui.py and stranica.py sources before patching. Cover photo and video removal, their related database updates, rebuilds, reload/main and fallback HTML writes. Acquire in the synchronous worker that actually mutates files; do not hold the fence in an event loop while waiting for another worker to reacquire it.

Inspect the actual call graph and lock ordering, including SQLite and spec84. Existing publish_transaction_guard._exclusive_lock uses a separate flock; nesting it with this registry can self-deadlock. Every nested participant must use the same reviewed registry. All participants must preserve the lock inode: never unlink or replace it. Validation cannot prevent an uncooperative writer replacing the path after a grant.

New source does not contain already-loaded old processes. Complete writer inventory, drain, old/new loaded-source identity, canonical lifecycle recovery, full backup and exact request/manifest/Gate B/activation remain open. Do not run a new freshness preflight or install until integration and containment pass their actual gates.

## Private source integration candidate

`integrate_private_sources.py` now assembles a private candidate only when all
three authenticated current-source SHA-256 values match their pinned bytes. It
never edits the input directory and refuses a non-empty output directory. The
generated private files remain outside Git; only their sizes, hashes and the
sanitized integration/test evidence are retained here.

The integration moves photo/video remove-all mutations into synchronous
`asyncio.to_thread` workers that acquire the fence before any database or
filesystem mutation and hold it through rebuild. Low-level removal helpers
fail closed unless the same thread owns the fence. `stranica.main`, its final
writer and etalon writer acquire the same reentrant registry, so validation
fallback writes and the nested spec84 lock keep the required order. The legacy
transaction guard is rebound to that registry instead of opening a second
`flock` on the same path.

Thirteen new isolated integration tests cover the bound-hash fail-closed rule,
photo/video/diagnostic lock boundaries, exact SHA256-verified pre-mutation media
copies, deletion completeness, rollback, preservation of a changed after-image,
async worker delegation, direct `main` placement and shared legacy-guard
registry. Independent review found and closed the earlier best-effort backup
gap before accepting these isolated boundaries. This proves only the
assembled private candidate. It is not installed, does not exclude old loaded
processes, and is not a writer Gate or production receipt.


## Emergency007 point3 — current isolated candidate

The current source-bound manifest, boundary report and 41-test output are in
`handoff006_evidence/emergency007_point3/`. Build with `--dependency-dir` pointing
to the four exact private dependencies recovered in point2. All seven original
input hashes are checked. Private inputs and generated private source files
remain outside Git; this repository holds only the builder and sanitized evidence.

The candidate restores CRM fields using SQLite compare-and-swap, records the
actual media helper changes inside its write transaction, and reverses only
matching after-images. Video recovery includes media rows and the vehicle cache
member. Other vehicles, changed operator values and newly created media files
are preserved. Backups/restores use bounded 1 MiB reads, no-follow directory
handles, hash checks, original permissions and atomic no-replace restoration.

The real HTML fallback and missing-media abort now signal failure rather than
letting the caller report a successful rebuild. Direct spec84 entry obtains
the publication fence first; renderer SQLite reads can occur under spec84.
Media write transactions finish before entering rebuild/spec84. The legacy
publication guard uses the same reentrant registry and preserves the lock inode.

The earlier integration self-review is not independent acceptance. Point4 must
review this candidate independently, including the documented fixture limits
and full release closure. Old loaded writers, canonical backup/Gate/install and
production recovery remain separate work. No installation or product criterion
is accepted by these isolated checks.
