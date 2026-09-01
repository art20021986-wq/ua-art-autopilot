# TASK105 — Controlled FAST Production Canary

## Owner authorization

Exact owner command received on 2026-09-01:

> «УТВЕРЖДАЮ КОНТРОЛИРУЕМЫЙ FAST PRODUCTION CANARY: одна низкорисковая операция, обязательный backup, live-проверка и автоматический откат при любой ошибке.»

## Authorized operation

Create or atomically replace exactly one dedicated, non-business static marker:

- production filesystem target: `/home/Carix/video/task105-fast-canary.txt`
- public verification URL: `https://www.uaart.com.ua/video/task105-fast-canary.txt`
- resource lock: existing global production-writer lock for bootstrap safety
- AI route: `NO_AI`

The marker is isolated from all existing pages, cards, CRM records, media, application code, Cloudflare and DNS. It exists only to prove the new FAST path can perform one bounded production transaction and produce a truthful final receipt.

## Mandatory transaction

1. Confirm the task is classified `FAST / NO_AI`.
2. Compile and run deterministic tests.
3. Capture the exact prior target state: existing bytes or verified absence.
4. Create a durable backup manifest under `/home/Carix/backups/task_105_fast_canary/`.
5. Hash protected production files before write:
   - `/home/Carix/crm.db`
   - `/home/Carix/video/index.html`
   - `/home/Carix/video/katalog.html`
6. Atomically write only `/home/Carix/video/task105-fast-canary.txt`.
7. Verify exact local readback and unchanged protected-file hashes.
8. Verify the unique marker publicly immediately and after a delayed check.
9. Confirm the public home and catalog still return HTTP 200.
10. Produce a canonical production receipt validated by `automation/task_orchestrator.py`.

## Automatic rollback

After a successful production write, any failed invariant or live check must automatically:

- restore the prior marker bytes when it existed; or
- delete the marker when the prior state was absence;
- verify the rollback publicly;
- return `ROLLED_BACK`, never `FINISHED`.

## Hard boundaries

- Existing site-page write: **NO**
- CRM/database write: **NO**
- Existing media write: **NO**
- Cloudflare write: **NO**
- DNS write: **NO**
- Production target count: **1**
- Runtime LLM calls/tokens: **0**
- Blind retry after logical/safety failure: **NO**

## Acceptance

The canary is accepted only when:

- backup exists and is hash-verified;
- exactly one production target is changed;
- protected production files are byte-identical before/after;
- immediate and delayed public marker checks pass;
- public home and catalog checks pass;
- unexpected changes = 0;
- rollback path is verified ready;
- final receipt passes the central orchestrator validator.
