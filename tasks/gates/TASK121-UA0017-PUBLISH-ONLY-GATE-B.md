# Gate B — TASK121 / UA-ART-UA0017-PUBLISH-ONLY-001 v1.0

**Status: HOLD — Production authorization MUST NOT be issued yet.**

## Scope verified
- Branch: `ua0017-publish-only-001`
- Base main SHA: `af683ac6236dcbf7a70e56183de7134d5af4b6b7`
- Task specification commit: `10f257bc539ca97a14536530e9632fb14d61d37b`
- Target: UA-0017 only
- UA-0018 target changes: 0 planned
- Production changes performed by TASK121 preparation: 0

## Prior failure root cause — VERIFIED
The previous two-card TASK120 ended `ABORTED_NO_PRODUCTION_WRITE`.
- backup job conclusion: failure
- failure code: `MUTATING_ALWAYS_ON_UNAVAILABLE`
- temporary Always-On POST produced no usable trigger id
- backup mode did not start
- transaction never promoted to OPEN
- Production controller did not run
- UA-0017/UA-0018 CRM, card, media and public-site writes did not occur
- rollback controller did not run because there was no Production mutation to roll back

Therefore TASK120 is not evidence that UA-0017 was published; it is evidence that the operation aborted before Production write.

## Existing TASK120 package reuse audit — FAIL FOR SINGLE-CARD EXECUTION
The existing controller is cryptographically/task-contract bound to `TASK120-PUBLISH-UA-0017-UA-0018` and contains an `EXPECTED_TARGETS` mapping for both UA-0017 and UA-0018. Its request, manifest, receipt and remote transport identities are also TASK120-specific. It MUST NOT be executed as the new UA-0017-only operation without a newly verified single-card package.

## UA-0017 reference facts available from verified repository evidence
TASK120 reference data binds UA-0017 to:
- CRM internal id 26
- VIN `WAUZZZ4GXGN069684`
- Audi A6
- CRM year 2015
- mileage 118000 km
- referenced status `ge_waiting`
- referenced media count: 39 JPEG photos, 0 video

These are reference facts for preparation only. They MUST be refreshed from authenticated CRM immediately before any future Production authorization and MUST NOT overwrite newer values.

## Additional specification integrity — HOLD
Prior TASK120 planned 18 model-level rows using a 2016 Audi source document while the CRM vehicle is year 2015. Those rows cannot be represented as VIN-specific equipment of this exact UA-0017 unless independently verified. Future package must label model-level reference data honestly and preserve verified vehicle facts separately.

## Current preparation checks
| Check | Result |
|---|---|
| Separate branch created | PASS |
| Main/Production modified by TASK121 preparation | PASS — 0 writes |
| UA-0018 excluded by new task specification | PASS |
| Prior TASK120 root cause identified | PASS |
| Existing two-card controller safe to reuse as-is for single card | FAIL — prohibited |
| Fresh authenticated CRM/media/spec snapshot | NOT YET VERIFIED |
| New UA-0017-only executable package with allowed provenance | NOT YET PRESENT |
| Sandbox/preview package tests | NOT RUN — package absent |
| UA-0018 mutation paths = 0 in executable package | NOT VERIFIABLE — package absent |
| Future execution mechanism resolves prior Always-On blocker | NOT YET VERIFIED |
| Production authorization for TASK121 | PASS — ABSENT |

## Why Gate B is HOLD
Gate B cannot truthfully be marked PASS until there is:
1. a fresh authenticated read-only snapshot of UA-0017 and its current media/spec/publication state;
2. a newly task-bound UA-0017-only executable package with allowed provenance;
3. passing sandbox/preview tests proving zero UA-0018/non-target mutation paths;
4. a verified safe execution mechanism for the future Production step that does not repeat or bypass the `MUTATING_ALWAYS_ON_UNAVAILABLE` failure.

## Owner action now
**No Production command is requested yet.** Do not send `ПУБЛИКОВАТЬ UA-0017` until this Gate B is replaced by a verified `PASS` report.

## Production lock
TASK121 preparation is non-Production. No old TASK120 authorization may be reused. Any future Production authorization must be newly bound to TASK121 / UA-0017 only and issued after Gate B PASS.
