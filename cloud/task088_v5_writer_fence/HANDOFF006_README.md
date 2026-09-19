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
