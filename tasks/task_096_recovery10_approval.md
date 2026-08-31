# TASK 096 — recovery authorization, 2026-08-31

OWNER_APPROVED: YES
APPROVED_AT_UTC: 2026-08-31T00:23:25Z
MAX_TRANSIENT_RETRIES: 10
PRODUCTION_AUTHORIZED: NO

## Exact latest owner instruction

> Если нужно включайте 10 атозвпусков, почему остановились ?

This extends the retry limit for the already approved TASK 096 DATA-ENRICHMENT SANDBOX only. The original scope in tasks/task_096_data_enrichment_approval.md remains unchanged: UA-0015 data-canary first; UA-0001 through UA-0016 only after its real PASS; no production, public site, bot, primary-field, or live CRM writes.

## Execution limits

- Repair the PythonAnywhere launcher instead of repeating send_input to an unstarted console.
- Use disposable scheduled one-shot tasks through the existing authorized API credential. Never modify or delete pre-existing user tasks or consoles.
- At most ten transient-error stage retries in the recovery execution, shared across stages. Successful stages are not restarted.
- Authentication/authorization failures, ambiguous execution, data-integrity violations and unconfirmed technical facts are stop conditions, not reasons for blind retries.
- Each scheduled command has an expiration, a lock and a completion marker. Only its own created task is removed afterward.
- Purchase/cost/auction/wholesale prices must not be selected into the context, sent to AI, logged or stored by enrichment.
- Disable any hard-coded technical fallback. Facts require actual fetched source evidence; insufficient evidence is not PASS.
- Preserve manual CRM fields. Apply only to the closed existing TASK096 sandbox database.
- No automatic publication, live database updates, service restarts or public preview deployment.
- Write sanitized stage progress, final evidence and, only after real successful enrichment, the UA-0015 preview.
