# UA-0012/UA-0013 publication transaction repair

STATUS: **PASS — production verified**

Completed: 2026-08-29 UTC

## Result

- UA-0012 (Kia K5 2018): published once, stage **2**, category **more**, customer label **На пароме**.
- UA-0013 (Mercedes-Benz Б-КЛАССА 2015): published once, stage **2**, category **more**, customer label **На пароме**.
- Public catalog contains **13** published cars. UA-0012 and UA-0013 each have exactly one catalog card.
- UA-0014 remains an unfinished CRM draft with `published=0` and is absent from the public catalog.
- Both primary pages contain the correct VIN, one matching diagnostics link, and the stage-2 contract.
- Both diagnostics pages are public and return complete HTML.
- The CRM bot was restarted and returned to `Running`; fresh heartbeat jobs executed successfully.
- Production install receipt: **PASS**.
- Read-only postcheck after restart: **PASS**.
- CRM rows changed by deployment: **NO**.
- Runtime LLM tokens: **0**.

## Root causes

1. `cars_ui.toggle_publish` ignored the publisher's boolean result and sent a false success message.
2. The publisher/SEO chain required a diagnostics target before the target could be staged, and the legacy diagnostics heading did not satisfy its own case-sensitive validator.
3. The final shared-catalog processor enumerated every CRM identifier, including unpublished drafts. When UA-0014 was created with `published=0`, it was incorrectly injected into the candidate catalog.

## Permanent safeguards

- Publication now stages diagnostics first and publishes the primary pages plus both catalogs as one locked transaction.
- Any failed validation restores the bounded file snapshot and the CRM publish preimage, and the bot sends only the real final result.
- Catalog generation is fail-closed and admits only rows with `published=1`.
- A generated catalog containing an unexpected identifier is rejected before production write.
- The package verifies exact card counts, stages, diagnostics links, protected-page hashes, both site roots, SQLite integrity, and CRM row hashes.
- Contract coverage includes the unpublished-draft regression (`UA-0014`).

## Independent public verification

- Live read-only check: **PASS** at `2026-08-29T10:18:30Z`.
- Catalog: 13 unique cards, exactly one UA-0012 and one UA-0013.
- UA-0012 and UA-0013: stage 2, customer label «На пароме», primary and diagnostics pages open at their expected paths.
- Delayed cache-busted catalog recheck: **PASS**.
- Evidence: `cloud/task_083_publish_transaction/evidence/public_live_verification_20260829T101830Z.json`.
