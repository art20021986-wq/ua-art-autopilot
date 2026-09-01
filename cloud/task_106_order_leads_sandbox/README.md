# TASK 106 — Order Leads Sandbox

This package is the first implementation round for the owner-approved specifications:

- `UA-CRM-ORDER-LEADS-001`
- `UA-SITE-BOT-ORDER-FORM-001`

It intentionally implements only a mock CRM contract and additive schema in an isolated GitHub branch. It does not connect to the live CRM, site, bot, PythonAnywhere or Production.

## Architecture

- `clients` represents one person/contact.
- `order_requests` represents one request for an automobile under order.
- One client may have many requests.
- A raw request never creates a row in `cars`.
- Conversion into an unpublished automobile draft is a later gated operation after purchase confirmation.

## Files

- `UA_CRM_ORDER_LEADS_001_v1.0_APPROVAL.md` — approved CRM specification.
- `UA_SITE_BOT_ORDER_FORM_001_v1.0_APPROVAL.md` — approved site/client-bot specification.
- `order_lead_contract.schema.json` — normalized site/bot payload contract.
- `schema_order_requests.sql` — additive Sandbox schema blueprint.
- `mock_crm.py` — fail-closed mock ingestion service.
- `test_mock_crm.py` — idempotency, validation and isolation tests.

## Run locally

```bash
python3 -m unittest -v cloud/task_106_order_leads_sandbox/test_mock_crm.py
```

Expected final state for this round:

`TASK106 CONTRACT/MOCK PASS · ONE SUBMIT = ONE LEAD · PRODUCTION WRITE: NO`

