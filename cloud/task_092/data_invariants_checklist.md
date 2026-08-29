# Data Invariants Checklist (Task 092)

Each invariant below must be checked by an automated validator against the temp build (see `atomic_build_contract.md`, step 7). Status column reflects that no real build exists yet this round.

| # | Invariant | Automated check | Status this round |
|---|---|---|---|
| 1 | total == count of unique published cards | count(published==true, distinct id) == homepage.total | PENDING — no real data |
| 2 | total == Korea + Sea + Georgia + Kyiv | sum(stage buckets) == total | PENDING |
| 3 | each car in exactly one stage | no id appears in >1 stage bucket | PENDING |
| 4 | ID and VIN unique | no duplicate id or vin across registry | PENDING |
| 5 | stage homepage == catalog == card | compare stage field rendered on all 3 surfaces per id | PENDING |
| 6 | ETA catalog == card | compare eta_kiev rendered on catalog vs card per id | PENDING — this is the known UA-0009 failure |
| 7 | days catalog == card | compare computed days on catalog vs card per id | PENDING — this is the known UA-0009 failure |
| 8 | photo/video counts match real files | count(existing non-zero-size files) == displayed count | PENDING |
| 9 | cover exists and non-zero size | stat(cover_photo).size > 0 | PENDING |
| 10 | stage 1 (Korea) has no public container/ETA/days | assert fields absent in rendered HTML | PENDING |
| 11 | stage 4 (Kyiv) has no public container/ETA/days | assert fields absent in rendered HTML | PENDING |
| 12 | exactly one public WhatsApp/Chat element per page | count(dom selector) == 1 | PENDING |
| 13 | build_id consistent across homepage/catalog/cards | single build_id value across all generated files | PENDING |
| 14 | single active language rendered (no simultaneous RU+UA) | exactly one language block visible per request | PENDING |

Any row not marked PASS blocks release to canary, and blocks any request to proceed to production regardless of round.
