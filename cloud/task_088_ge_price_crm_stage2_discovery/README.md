# TASK088 Stage 2: read-only discovery

This package reads current CRM source before preparing the Stage 2 change in
UA-ART-GE-UA-MARKET-PRICE-001 v4.0. It makes no remote writes, starts no process,
does not read vehicle records, and does not restart Telegram or the website.

Its identity is `TASK088-GE-PRICE-CRM-STAGE2-DISCOVERY`. A completed discovery
receipt means only that the source inspection completed. It is never evidence
that Stage 2 input, persistence, live schema, or Telegram acceptance passed.
The final identity `TASK088-GE-PRICE-CRM-STAGE2` remains separate.

The existing Stage 1 receipt is an immutable prerequisite. Its functional
result is retained. The previous Stage 2 request cannot be replayed: it points
to the Stage 1 controller and receipt. The old installer also does not implement
the Stage 2 acceptance tests. All prior markers, receipts and ledgers remain.

The request uses the existing STANDARD read-only workflow and its existing
nonproduction PythonAnywhere connection for GET requests. It does not alter
workflow definitions, credential routing, runtime manifests or replay policy.
Source snippets are restricted and checked before export; full source/config
files and raw database contents are not exported.

Subsequent live CRM writes require their own reviewed Stage 2 package and the
existing production gates, backup, database verification and rollback checks.
Website Stage 3 requires the owner's separate permission under v4.0.
