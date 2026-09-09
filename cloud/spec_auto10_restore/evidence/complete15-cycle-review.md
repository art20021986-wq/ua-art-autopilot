# Independent review: combined final-15 synthetic cycle

Review date: 2026-09-09. Scope: `complete15_cycle.py`, its frozen publisher dependency, and the synthetic server launcher/package builder. Result: **PASS for isolated synthetic execution; overall Gate B is NOT EVALUATED.** No production deployment, service change, or external source request was performed by this review.

## Reviewed byte bindings

| File | SHA-256 |
| --- | --- |
| complete15_cycle.py | d6449d1c53a65d02371d00bab78cb3cf5fe7231d644964f312ce915dd1bf851d |
| complete15_server_gate.py | 78fc3c047eb36d31bba6a282b1147c25fc7c071b0ea12b85f1a603cc7733812e |
| package_complete15_cycle.py | f390c4943f05d221ec796fe5f78d2b70efdf4118ad48952a82aed55d41e72e3f |
| full_publisher_rehearsal.py | 8f8597a64c85f8b34ad36bc9855606b0bf8d45de5b3bcce9e5ea2b0d6bcd2f4f |

Final candidate manifest: `c4f75a818156e29426c9d601552ab0de56663e965233f2a56c01f5aaa111de07`.

The candidate directory must contain precisely its fifteen manifest-pinned modules and manifest. Execution dependencies are separately pinned. Input reads reject symlinks, nonregular files, and changing/replaced inodes. Application source is captured and relocated into an exclusive stage with AST-equivalent literal substitutions; no candidate function is replaced. The frozen publisher helper is executed from the captured, verified bytes. Its only replaced function is the synthetic seed fixture in its test namespace.

The launcher uses a fresh isolated Python 3.10 child (`-I -B`), bounded timeout and minimal environment. The inherited Python audit guard rejects external writes/reads, network and child processes after preparation. This is a guard for audited Python code, not a sandbox for hostile native extensions. The launcher verifies the exact bundle member set and watches candidate/dependency bytes, mtimes and inodes through execution.

## Findings resolved during review

1. The original mileage assertion accepted any `101` substring in HTML. It now requires the exact mileage table row showing `101 234 км`; specification facts are compared before/after editing.
2. Initial checks tested page deletion only immediately after the delete call. Explicit absence checks now follow rejected publication of the retired UID, publication of the next UID, its repeated publication, and rollback of a later publication failure. The server launcher independently checks retired-page absence after its child exits and fails on any retained page.
3. The initial helper import reread the file after hashing. It now compiles the captured, verified helper bytes directly, closing that check/use gap.

## Evidence inspected

The final local run `/tmp/ua-art-complete15-cycle-final04/result.json` completed at `2026-09-09T09:17:03.587704+00:00`, with status PASS and all four I/O counters zero. Its SHA-256 is `189dc9ad24138cd724d127c58d1175cc656009001042154f9acd5d3a60573785`. The synchronous parent readback records child exit code 0 and no retired pages after child exit; SHA-256 `6c0f72da04be7d58e1b590c148de0178908f8d1fbcfb8e6aeb33d1ced66731d3`. An independent subsequent execution also found no retired pages in either root and no retired-write audit log.

The run exercises actual staged `db.create_card`, selected `ai_filter` clean/store functions, publication, manual field preservation, deletion/archive retention, UID allocation after deletion, new publication and repetition. The frozen publisher scenario retains its eight negative controls and nonvacuous rollback check. A second fault is injected after deletion: UA-0003's fixture price changes from 15000 to 16000, and the second catalog write fails after five HTML files actually change. The real transaction restores exactly those five files; all HTML matches the pre-failure bytes and the deleted UA-0002 URLs remain absent. The price is then returned to its original fixture value. No candidate validator or production function is bypassed; only the synthetic one-shot write fault is injected and removed.

Final live identities inside the fixture are UA-0001 and UA-0003; UA-0002 is retired. Each retained primary page validates the specification, one VIN and the existing pinned shell; catalogs retain the golden shell and exact intended UID set.

## Material limits

Earlier runs under the shared workspace showed four deleted fixture HTML files restored after successful child and parent readbacks. Extra retired-write auditing and a fresh run under `/tmp` distinguished this workspace artifact discrepancy from the tested candidate: the final run, synchronous parent readback and independent subsequent filesystem read all preserve deletion, with no retired Python write event logged. The exact component responsible for restoring workspace artifacts is not identified. No application runtime patch was made in response. Preserve the final receipts and retain the server launcher's independent post-child readback; do not substitute stale earlier workspace directories for execution evidence.

All data is synthetic. Fifteen modules are staged/compiled; `cars_ui` is not imported and `ai_filter` runs only the explicitly listed actual AST functions. Telegram callbacks, the running worker, real external sources, all production cards, server restart, external-writer exclusion and deployment remain separate gates. This review neither grants Gate B PASS nor authorizes removal of HALT or a production publication.
