# One-click publication candidate

**Installed through main Actions 36301475826 (SUCCESS), 2026-09-27 07:13 UTC.**
Owner authorized the repair on 2026-09-27. The source-only deployment and subsequent
UA-0021 publication are recorded in `cloud/crm_oneclick_release_001/post_install_acceptance.json`.
Full manual Telegram journey and normal-quota latency acceptance remain separate.
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

## Release and current verification

The prior delivery incident was reconciled through its registered route at
2026-09-27 06:33 UTC. The composed four-file release passed Gate B, backup,
installation, restart and verification in main Actions 36301475826. Its transaction
is FINISHED. Do not replay the original delivery or oneclick launch.

Read-only verification at 2026-09-27 08:21 UTC found UA-0021 (cars.id=31) in the
public catalog at the ferry stage, with its retry cleared. Both ordinary public
URLs matched the current server HTML. All 21 active published CRM cars matched
the catalog, with counts korea=4, ferry=5, georgia=6, kyiv=6. The external browser
also rendered the catalog and UA-0021 normally. The four installed source hashes
still match the release receipt.

The CPU allowance is now 10000 seconds; the 08:21 UTC read-only observation was
129.829948 seconds used. This supersedes the old exhausted 5000-second allowance;
it is not proof of a measured Telegram response time.

An unrelated video-publisher transaction 36304601891 was performing its own
rollback and bot resume during this verification. Do not interfere with that
operation, launch another installer, clear its transaction, or discard pending
requests. Follow current `cloud/latest_status.md` and the release evidence.
