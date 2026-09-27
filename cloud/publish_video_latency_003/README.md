Publication stalls in the obsolete UA-MCF-DEDUP hook: each HTML alias triggers pairwise video frame extraction and possible media moves. Remove exactly that 19-line wrapper from the installed publisher. Existing page validation, renderers, request queue and transaction guards remain intact.

Reuse the reviewed source-only deployment lifecycle with a separate namespace and one-file plan. Exact input/dependency/output hashes, backup, writer locks, bot pause/resume, rollback and public health checks remain mandatory. Installation acceptance is distinct from actual UA-0020 publication acceptance.

Validation: 22 contract-compatible regression/lifecycle tests pass. The exact private publisher writer chain was separately exercised three times over canonical, alias, diagnostics and catalog writes; old hook called seven times including a rejected write, new hook zero; validation still rejects invalid writes.


First installation stopped before any source replacement with WORKER_BUSY. The inherited transport treated transitional Stopping as a completed shutdown. Retry R2 requires the explicit Stopped state before acquiring writer locks; the existing timeout, locks, backup, rollback and health gates remain enforced. Added a regression covering Running → Stopping → Stopped (22 total tests). The publisher candidate and its live-preview source/dependency hashes are unchanged.

R3 uses an independently refreshed authenticated production storage measurement (08:42:06 UTC), validated against the unchanged 30-minute freshness guard. R2 stopped before backup/transaction/source writes; its FAILED state and exact halt history are preserved. Original R1/R2 packages remain immutable. The actual publisher output is unchanged from the successful live preview.
