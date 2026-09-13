# Combined17 v2: isolated execution package

Candidate `UA-ART-SPEC-AUTO10-COMPLETE-17-V2` is a pure follow-up to the frozen
seventeen-file candidate. Its manifest SHA-256 is
`12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136`.
No production installation, HALT change, restart, task mutation or source
network request is performed by this package.

Two corrections are included. The optional analytics maintenance pass now
leaves primary card, diagnostic and catalog HTML untouched; the ordinary WSGI
response and analytics endpoint code are unchanged. vPIC response matching
now requires the returned VIN to match the requested car, in addition to the
existing model/year/error checks. Source domains remain unchanged.

The previous analytics coordination patch alone was insufficient: its real
maintenance pass appended an extra script to generated card pages and violated
the existing shell fingerprint. The failed frozen17-v1 evidence is retained
in `evidence/complete17-analytics-interaction-v1.json` and
`evidence/complete17-cycle-v1-local-failure.json`. No shell allowlist was widened.

The new pure assembler is `complete17_refined_candidate.py`. It verifies the
frozen base, both pure patchers, exact output hashes and seventeen target names.
The output is exclusive and receives its manifest last. All historical fifteen
and seventeen-file manifests, helpers and server receipts remain unchanged.

## Rehearsal

The new `complete17_cycle.py` imports the two old helpers only after verifying
their frozen SHA-256. It relocates captured source literals into an exclusive
test directory and uses the existing audit guard. It exercises:

- Actual card creation, publication, manual edit, deletion, rejection of a retired
  identifier, next-number allocation, publication and repeat publication.
- Two non-vacuous HTML write failures with actual rollback and absence of deleted
  primary/diagnostic URLs afterwards.
- Actual publisher lock exclusion of analytics and all three guarded TASK083
  entry functions, real optional analytics writing while holding that same lock,
  and real TASK083 atomic writing through its unchanged admission decorator.
- Durable intent exclusion for both external writers and an ordinary WSGI
  response while intent remains active.
- Preservation of ten generated canonical HTML files, both fixture databases,
  three saved media files, the existing shell assets, specification and one VIN.
- Actual new vPIC policy against an in-memory mismatched-VIN response. This is
  offline response validation, not confirmation of live source availability.

The old TASK083 installer requires at least eleven cars and special fleet
invariants. Its full fleet installation is not represented by this small cycle.
Admitted testing uses its real atomic writer and pure generator patch through
the exact admission decorator; the historical full installer is not reported
as successful. Kernel lock contention uses distinct real file descriptors in
one isolated process and is not proof that old production processes have drained.

Local execution in `/tmp` completed **PASS** at
`2026-09-09T10:51:32.413206+00:00`. Publisher, lifecycle, both rollback paths,
writers and offline VIN-response binding passed. All four prohibited-I/O
counters were zero. The result SHA-256 is
`c2bd4ef738144cad18d53f6692df3dfdbffa7e9e96f1a343181f98700c5c58d8`.
An independent subsequent read found no retired direct URLs.

Earlier runs in the shared workspace are retained as non-authoritative
diagnostics. The already documented workspace restoration discrepancy appeared
again; the exact external component is unknown. No application lifecycle code
was changed in response. See `evidence/complete17-workspace-run-diagnostics.json`
and the earlier `evidence/complete15-cycle-review.md`.

## Server package and command

Private ZIP: `uaart-complete17-cycle-v2.zip`, 237428 bytes, 23 members.
SHA-256: `e43e9b660d88e51fab8382a67b64d495ee444c6e64885946e5cd57aa737bdf66`.
Two independent package builds produced identical ZIP bytes.

After verifying that exact uploaded ZIP hash, extract once into the previously
absent directory `/home/Carix/spec_complete17_gate_20260909/bundle-v1`.
The directory must contain only the bundle's exact member set. Run:

```sh
python3.10 -I -B /home/Carix/spec_complete17_gate_20260909/bundle-v1/complete17_server_gate.py
```

The launcher requires Python 3.10 and its exact server path, validates the
candidate and all bundle files, and reads only three pinned live dependencies:
`stranica.py`, `catalog_design_guard.py`, and `catalog_design_golden.html`.
The child executes entirely in a new stage directory, with no production
application import or service action. The launcher compares input hashes,
mtimes and inodes afterwards and separately checks deleted URLs after child exit.
Read `result.json`, `server-summary.json` and `launcher.log` from the printed
unique `run-*` directory. A failed readback must not be labeled PASS.

## Actual PythonAnywhere result

The exact package completed PASS on Python 3.10.12 at
`2026-09-09T10:54:40.720872+00:00`, run directory
`/home/Carix/spec_complete17_gate_20260909/run-20260909T105408122485Z`.
Publisher, lifecycle, writers and both rollback paths passed; all four guarded
I/O counters were zero. Twenty-six watched inputs retained bytes, mtimes and
inodes. Deleted direct URLs were absent after the child exited. This is the
combined refined seventeen-file execution, with synthetic cards and databases.

Read `evidence/complete17-v2-server-result.json` (SHA-256
`613f8cb1a5ddbe07c9719f816e4725f58d3645adefd6d4c033abfc713cc8ab78`)
and `evidence/complete17-v2-server-server-summary.json` (SHA-256
`5d5d856d0d308413491f624e38c5d3142db2886239e3037f7c5d08035ed95672`).
The exported evidence ZIP was downloaded and checked against the SHA printed
in the authenticated server console. Production modules were not installed.

**Overall Gate B remains NOT EVALUATED by this package.** Production writer
drain/handoff, real source10 results, live worker behavior, existing card
restoration and UA-0017/UA-0018 publication require their own verified receipts.
