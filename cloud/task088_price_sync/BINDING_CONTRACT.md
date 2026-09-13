# Bounded price-event authority — candidate implementation

`uaart_price_sync_binding.py` is a real local verifier, not a successful deployment
receipt. Its tests use an isolated `TEST` root and synthetic evidence. No live
configuration, anchor, Telegram message or public mutation has been produced.

## Startup and trust chain

The verified installer writes a private anchor **last**, after a real installation
receipt. The existing CRM registration calls:

```python
from pathlib import Path
import uaart_price_sync_binding
uaart_price_sync_binding.bootstrap(
    app, anchor_path=Path('/home/Carix/.uaart_price_sync_anchor.json'))
```

`bootstrap` populates the existing application's runtime binding; it does not
register jobs, create another bot or claim acceptance. The runtime is registered
afterward. Bot identity is verified by a wrapper preserving the existing
`app.post_init`, after Telegram initializes the bot and before polling starts.
Publication cannot be authorized before that identity check. Custom application
lifecycle code must execute `post_init`; otherwise authorization stays closed.

The anchor has contract `UA-ART-PRICE-EVENT-ANCHOR-1`, an explicit root-relative
`config_path`, and `config_sha256`. An optional externally supplied
`expected_anchor_sha256` gives an additional installer pin. Both files must belong
to the current server user and have no group/other access. They are outside the
source files whose hashes they transitively contain.

The configuration contains `delegation` and `artifacts`. The delegation has
contract `UA-ART-PRICE-EVENT-DELEGATION-1`; its canonical JSON SHA is approved in
the canonical manifest's `price_event_delegation_sha256`. The ordinary canonical
request binds that manifest, Gate B and owner approval. The owner approval binds
the request subject with only `critical.owner_approval_sha256` zeroed, matching
the installer's cycle-free subject convention.

Every artifact is a separately read `{path, sha256}` reference. Required names:
`manifest`, `request`, `owner_approval`, `gate_b`, `deployment_receipt`,
`writer_fences`, `owner_private_chat`, `owner_policy`. The provider checks their
content relationships, not only their hashes or a `PASS` flag.

The installation receipt must contain the real install engine fields:
`task_id`, `transaction_id`, `request_sha256`, `manifest_sha256`, `gate_b_sha256`,
`installed_files_sha256`, `installed_schema_sha256`, `cars_audit_unchanged` and
status `INSTALLED_PENDING_LIVE_ACCEPTANCE` or `FINISHED`. Pending acceptance is
never represented as completed Stage 3. Canonical delegation must explicitly
allow `BOUNDED_PRICE_EVENTS` before even this bounded runtime is activated.

## Delegation fields

All server paths below are explicit, normalized relative paths beneath the fixed
production root `/home/Carix`. Tests must explicitly inject another root and use
environment `TEST`; they cannot load a production binding accidentally.

| Field | Required binding |
| --- | --- |
| `environment`, `root`, `task_id` | Production root and fresh Stage 3 identity |
| `operation` | `UPDATE_EXISTING_CARD_AND_CATALOG_PRICES` |
| `activation` | `BOUNDED_PRICE_EVENTS` |
| `initial_publication` | `OWNER_MANUAL` |
| `fields`, `currency` | `price_uah`, `price_georgia`; USD |
| `non_price_changes` | `FORBIDDEN` |
| `car_identities` | Exactly 18 immutable ID/code pairs, UA-0001…UA-0018 |
| `installed_code_sha256` | Every runtime module, source dependency and writer |
| `schema_sha256` | Exact installed SQLite schema, including triggers |
| `database_path`, `publication_lock`, `journal_root` | Actual reviewed server locations |
| `public_origin`, `surfaces` | Exact HTTPS card/catalog files and every served mirror |
| `owner_chat_id`, `bot_id` | Independently verified owner private chat and CRM bot |
| `owner_private_chat_fact_sha256` | Pinned raw private-chat evidence summary |
| `owner_policy` | Exact approved policy, also stored as an independent artifact |
| `writer_fence_report_sha256` | Actual installed writer audit, no uncovered writer |
| `authorization_ttl_ms` | Between 1,000 and 30,000 ms |
| `verified_recovery_successor_allowed` | Explicit reviewed recovery delegation |
| `control_contract` | Actual observed control semantics, described below |
| `detail_url` | Existing HTTPS detailed report location |

The private-chat summary references independent raw evidence. Both must agree on
owner user ID, private chat ID, chat type and bot ID. The production raw source is
`AUTHENTICATED_CRM_BOT_PRIVATE_CHAT`, with `observed_ms`; the test-only source
`SYNTHETIC_TEST` is rejected outside an explicitly injected test root.

## Live control gate

No control filenames or safe defaults are inferred. `control_contract` must name
all three observations: `mode`, `halt`, `revocation`. Each names a path and either
`JSON_FIELD` with an explicit list of field keys, or, for HALT only, an approved
`ABSENT_IS_CLEAR` interpretation. Mode must be exactly `AUTOMATIC`; JSON HALT and
revocation values must be boolean `false`. Missing/malformed fields fail closed.

`LOCAL_AUTHORITATIVE` is permitted only when the deployment evidence establishes
that those files are the authoritative controls. Otherwise `EXTERNAL_CACHE`
requires a reviewed, installed bridge whose `producer_path` is code-hash pinned,
an explicit source, and a freshness record. That record binds `observed_ms`, the
source and `observations_sha256` for the actual observed file hashes/values.
Maximum age is 1–60 seconds. Future, expired or mismatched observations cannot
authorize publication. The cache's expiry also limits each authorization expiry.

On this task's last observed server inspection, neither `EXECUTION_MODE.json`
nor `AUTOPILOT_HALT.json` existed beneath `/home/Carix`. **A trusted control bridge
and its observed contract remain required; this package does not manufacture
them or treat absent unconfigured files as clearance.**

Ordinary HALT/MANUAL/revocation or a stale operational cache blocks price events
through the runtime's durable failure path. It does not abort otherwise valid
CRM startup. Missing immutable installation artifacts still prevent activating
this unverified binding.

## Every event

Authorization rereads pinned configuration/artifacts, every installed source
hash, the exact schema, all immutable vehicle mappings and control state. It
independently reads the already committed SQLite claim and checks the event and
nonce. The shared publication lock must already be held.

It writes a private, fsynced authorization record under
`<journal_root>/authorizations/`. Event claim and transaction identities are
derived from deployment delegation + event key + nonce. The completed deployment
transaction is retained separately as provenance and is never reused as an
active transaction. Runtime backup, per-event journal, semantic readbacks and
publication receipt remain mandatory.

```python
result = uaart_price_sync_binding.preflight(anchor_path=explicit_anchor)
```

This inspection reads only. It returns `BLOCKED` or
`INSTALLED_BINDING_VERIFIED_PENDING_BOT_INITIALIZATION`; it never activates a
worker, writes an authorization, sends Telegram, or reports Stage 3 complete.

Validation: 28 isolated tests cover artifact-chain tampering, wrong vehicle and
bot identity, missing locks, schema/source drift, symlinks, duplicate JSON keys,
control revocation/HALT, stale/future external observations, raw chat evidence,
read-only preflight, and startup ordering.
