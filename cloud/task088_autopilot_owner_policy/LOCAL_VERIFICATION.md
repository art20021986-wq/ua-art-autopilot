# Local verification — 13 September 2026

Scope: pure policy candidate only. NOT a production receipt or Gate B.

Executed from the branch preparation directory:

```sh
python -B -m unittest discover -s cloud/task088_autopilot_owner_policy -p 'test_*.py' -q
```

Result after the owner's 5-minute start-delay answer: **47 tests, all PASS**.

Coverage includes immediate stop for transient and other failures; exact task/request/attempt/failure binding; stale/future evidence rejection; backup/rollback/gate conditions; prohibition of replay or action skipping; terminal task rejection; dependency receipt and resource isolation checks; rejection of malformed booleans and ambiguous resource scopes; failure/daily-only notification selection; reporting time configuration. Five additional tests verify RU/UA customs captions, contract consistency, independent USD price requirements and rejection of unsupported inputs without adding unconfirmed all-inclusive promises.

This does not exercise Telegram delivery, live CRM, server restart, workflow activation, 60-second price synchronization, production rollback or the seven failing main workflow-contract tests. The trusted integration adapter must produce and verify real evidence; unit-test fixtures are not such evidence.

Ten further tests cover the 300-second boundary, long-overdue readiness with a fresh state snapshot, separate 60-second pricing deadline, unapproved/blocked/running/terminal tasks, exact identity binding, notification keys per readiness episode, stale observations, invalid timestamps, timezone equivalence, malformed inputs, and notification selection without progress chatter or delay of immediate failure handling. Deduplication here is a pure eligibility decision; live durable dispatch/delivery remains unimplemented.
