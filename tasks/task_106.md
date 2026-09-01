TASK_ID: task_106
SPEC_CODES: UA-CRM-ORDER-LEADS-001, UA-SITE-BOT-ORDER-FORM-001
SPEC_VERSION: 1.0 — APPROVED
OWNER_APPROVED: YES
DEFAULT_LANGUAGE: uk
SANDBOX_PREVIEW_ONLY: YES
PRODUCTION_WRITE_AUTHORIZED: NO
CRM_WRITE_AUTHORIZED: NO
BOT_PRODUCTION_WRITE_AUTHORIZED: NO
OWNER: Артём Бровинский / UA ART COMPANY LLC
DATE: 2026-09-01

# TASK 106 — Unified order leads for site, client bot and CRM

## Owner approval

The owner approved both specifications on 2026-09-01:

- `УТВЕРЖДАЮ UA-CRM-ORDER-LEADS-001`
- `УТВЕРЖДАЮ UA-SITE-BOT-ORDER-FORM-001`

## Scope for this round

Implement and verify only the isolated contract and mock CRM layer:

1. one shared request contract for site and Telegram client bot;
2. additive `order_requests` schema linked to existing `clients`;
3. idempotency by `request_id` and `source_event_id`;
4. eight order-country codes and `uk/ru/ka` language whitelist;
5. minimum fields: name, one contact, requested model or vehicle type, budget, delivery country and city;
6. multiple order requests per client;
7. no `cars` row at lead stage;
8. tests proving one submit creates one lead.

## Hard isolation

- Work only on branch `task106-order-leads-sandbox`.
- Do not merge to `main`.
- Do not write to live CRM, production site, client bot, PythonAnywhere production paths, Cloudflare production, or DNS.
- Do not deploy or restart services.
- Do not modify UA-0001…UA-0016, card templates, generators, media, diagnostics, or catalog stages.
- `order_country_code=georgia` is a purchase country and must never map to catalog stage `В Грузии`.
- Do not overwrite `cloud/latest_status.md` or `cloud/owner_reply.md` while another queued task owns those shared files.

## Dependency guard

TASK096 additional-card-characteristics run `33471128051` did not pass its final 16-card gate. Its production flags are false, but several cards have `NO_CONFIDENT_MATCH`, including UA-0009. Therefore this round must not touch card data or card rendering files. Preview integration against real card templates is deferred until a stable card baseline is available.

## Acceptance for this round

- Mock schema applies to an empty isolated SQLite database.
- All eight country codes are accepted.
- `uk`, `ru`, `ka` are accepted; missing language normalizes to `uk`.
- Unknown country/language is rejected safely.
- Duplicate request ID creates one order request.
- Duplicate source event creates one order request.
- One client may have two distinct order requests.
- Delivery country/city and at least one contact are required.
- Telegram ID is a valid contact for a Telegram-bot request.
- No `cars` table or car record is created by the mock ingestion path.
- Unit tests pass in GitHub Actions on the isolated branch.
- `PRODUCTION WRITE: NO`.

