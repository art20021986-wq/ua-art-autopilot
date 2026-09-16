# Combined17 rehearsal harness independent review

Date: 2026-09-09. Scope: static review and syntax parsing of the combined synthetic rehearsal, server launcher and deterministic packager. No live API, browser, production execution or deployment was performed by this reviewer.

Result: **PASS for the reviewed harness scope; final candidate manifest repin and actual execution remain pending.** No hard I/O safety defect was found in the trusted, hash-pinned rehearsal. This is not an overall Gate B approval.

## Reviewed source hashes

| File | SHA-256 |
| --- | --- |
| complete17_cycle.py | 54fa06b2fbf80258b3e7b484a5fbfb4705e6b53745f96c1ee92b912ce1e43867 |
| complete17_server_gate.py | 6a515057f22f785792342f65ffd00308511dd38cf7c804a184c7f9fb56d7c3b5 |
| package_complete17_cycle.py | 6a3e58250469b3fe69b0a3c035e708658ea662634c8a9b552010c0a52d902cda |
| complete15_cycle.py (frozen) | d6449d1c53a65d02371d00bab78cb3cf5fe7231d644964f312ce915dd1bf851d |
| full_publisher_rehearsal.py (frozen) | 8f8597a64c85f8b34ad36bc9855606b0bf8d45de5b3bcce9e5ea2b0d6bcd2f4f |

At review, all three new runners still bind candidate manifest `d800e55813b6edc24322f7021e924dd0052915f07414b42bd02f0a7c234522f5`; the corrected candidate requires an explicit coordinated repin. The two frozen helpers match their expected hashes and must remain unchanged.

## Findings resolved

- Ordinary WSGI response execution now occurs while the synthetic durable intent still exists. The harness checks the application response, zero analytics admission and unchanged HTML before removing the intent.
- The packager parses both new runner sources and rejects a missing, duplicated or mismatched literal `MANIFEST_SHA` assignment before ZIP creation.
- Writer interaction additionally compares both synthetic CRM/specification database bytes and the saved photo-tree file set and hashes before and after execution.

## Evidence and limits

Independent opens of the same lock inode exercise actual kernel `flock` contention, even within one Python process. The publisher blocks actual guarded TASK083 entry points and analytics; admitted writer probes inspect the held lock and preserve canonical pages. The launcher verifies exact staged file membership, pinned dependencies, byte/mtime/inode preservation and absent retired direct URLs after its child exits. ZIP member order, metadata and timestamps are fixed and output creation is exclusive.

The preserved v1 failure is meaningful: canonical HTML comparison detected analytics injecting a script into primary and diagnostic pages despite zero prohibited-I/O counters. It must not be relabelled as a successful execution of the corrected candidate.

The Python audit hook is confinement for reviewed Python code, not a hostile-native-code security boundary. Synthetic cooperative interaction does not prove legacy process drain, cross-host exclusion, a full historical TASK083 fleet installation, live source availability, production publication, worker SLA or overall Gate B.

## Final17-v2 follow-up review

The earlier hashes and pending statements above describe the historical review checkpoint. This follow-up verifies the refined candidate manifest `12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136`. All three new runner constants now bind this exact manifest. The frozen helpers remain unchanged.

| File | Final reviewed SHA-256 |
| --- | --- |
| complete17_cycle.py | fa9c104aeeb3f00d7d25ed7cc54e3bad247caac7b069333f486e86a7f0638fd0 |
| complete17_server_gate.py | 292b581d0aaa12d0ce109c6634331a82b8ebe83e0145b321c710fbe468b3022b |
| package_complete17_cycle.py | a2c687573232e8ef157c3dd2993dee6d87c740b7e8d1d83ea885cd8cc0753d42 |
| complete17_refined_candidate.py | 4ac3d242917a6b272f2cff9bbfa6a0fdc552de73593f6ba9e02d43b04e5f3420 |
| repair_analytics_shell.py | 184976fe95978be2d7de64455bfc40e83a3fb541c4029a084662b0d1358a0135 |
| repair_vpic_identity.py (verified helper binding; separate source-policy review) | 22829322363c6622fd477c5746b047e73f0c5bc8f36137b58db39f233ce0d654 |

The analytics follow-up accepts only its exact reviewed input and skips publisher-owned canonical card, diagnostic and catalog files. Its exact replacement preserves the WSGI response function AST. The refined assembler verifies its frozen base and both pure patchers, preserves the other fifteen module bytes, uses exclusive output creation and writes the manifest last. Candidate manifest claims are reconstructed from reviewed inputs and compared in full; they are not accepted as arbitrary self-reported approvals.

Independently executed bounded pure checks passed: actual v2 verification; rejection of forged overall Gate B PASS; rejection of an extra candidate file; rejection of an existing output without changing its bytes; exact expected analytics output; rejection of tampered analytics input; agreement of all three final runner manifest pins. These checks used temporary copies and performed no production operations.

The reviewer read the existing local combined execution result, without rerunning the full cycle: Python 3.12.14, completed `2026-09-09T10:51:32.413206+00:00`, report SHA-256 `c2bd4ef738144cad18d53f6692df3dfdbffa7e9e96f1a343181f98700c5c58d8`. Publisher, lifecycle, cooperative writers and offline source-identity binding all report PASS for the exact final v2 manifest. Network, outside-read, outside-write and process violation counters are all zero. The result explicitly states `production_changed: false` and `overall_gate_b: NOT_EVALUATED`.

**Final review result: PASS for pure assembly, exact pin agreement and the reported local synthetic execution scope.** Server Python 3.10 execution, legacy process drain/handoff, live ten-source acceptance and production publication remain separate gates; this review does not certify them.
