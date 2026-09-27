# One-click publication candidate

**Not installed. Gate B is not ready.** Owner authorized the repair on 2026-09-27.
See `tasks/UA-ART-CRM-ONECLICK-PUBLISH-001.md` for the critical specification,
confirmed causes, acceptance conditions and current deployment blockers.

This builder composes the existing stage recovery and performance builders; it
does not overwrite them with a separate old UI or worker. It removes the copied-ad
detour and the buyer preview from new CRM views, makes publication an explicit
idempotent intent, and adds durable requests and Telegram completion receipts.
The existing audited CRM update API enables a draft. The existing transactional
worker remains the only renderer; its backoff, locks, backup and public checks stay.

The code does not delete already-sent Telegram messages. Old ambiguous `car_pub`
and preview callbacks are inert. The separate hide action remains available on
newly rendered published-card screens through `car_hide`; a repeated hide cannot
toggle an already hidden car back on. Sold/delete retain existing independent routes.

The receipt store is private runtime data, outside crm.db, in
`/home/Carix/.crm_publish_requests/requests.sqlite3`. Include it in the release's
backup/rollback design without discarding pending operator work. It must never
be committed to the public repository. No new third-party dependency is needed.

The publication request is accepted after the audited CRM write and durable
enqueue. An interruption before acceptance may require a repeat click; the
existing reconciler still detects a committed draft activation. A queued request
and its terminal receipt survive restarts. A Telegram outage retries delivery;
it does not roll back a verified publication. The receipt job requires JobQueue.

## Reproduce

Run the four suites separately, because their historic modules share names:

```bash
python3 -B -m unittest discover -s cloud/crm_oneclick_publish_001 -p 'test_*.py'
python3 -B -m unittest discover -s cloud/crm_performance_001 -p 'test_*.py'
python3 -B -m unittest discover -s cloud/stage_edit_recovery_001 -p 'test_*.py'
python3 -B -m unittest discover -s cloud/delivery_status_001 -p test_delivery_status.py
```

68 tests pass (28 + 15 + 18 + 7). These are isolated regressions, not live
acceptance. Public request completion requires `verify_public` and an unchanged
CRM revision. The current revision implementation still has the separate media
limitations documented by PR128; this task does not claim to fix those.

`build(sources, dependencies)` accepts the exact byte dictionaries described by
`candidate_manifest.json`. All outputs compile. Build privately from current
production source snapshots; do not commit whole private runtime files. The
included fixtures are safe source excerpts and the credential-free old worker.

## Release remains blocked

The existing delivery incident is EMERGENCY_HALT / ROLLING_BACK. Use its registered
recovery with the ledger-bound nonce; do not clear markers, weaken checks, replay
the old installer or repurpose TASK120-only recovery. PythonAnywhere CPU quota is
exhausted (latest dashboard 8716.57/5000). CLAUDE.md defers heavy work at >=85%.
After recovery and a fresh resource check: reconcile current sources and PR128,
rehearse exact backup/install/rollback, pass Gate B, deploy through main Actions,
confirm bot code loading and verify UA-0021, catalog, counters and actual browsers.
No production launch or new delayed deployment is included in this candidate.
