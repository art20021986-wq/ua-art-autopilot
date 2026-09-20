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

## FINAL v5.0 dynamic operation delegation

The v1 contract above remains unchanged for its bounded historical candidate.
The new contract `UA-ART-PRICE-EVENT-DELEGATION-2` uses operation
`UPDATE_PUBLISHED_CAR_HOME_CATALOG_PRICES`. Its manifest must explicitly bind
`identity_policy: AUTHENTICATED_CRM_PUBLISHED_CARS`; this does not silently extend
an existing v1 approval. All existing immutable artifact, source, schema, bot,
writer fence and fresh canonical control checks still apply.

`car_identities` now pins the initial unique ID/code pairs without requiring 18
cars. A newly published car is admitted by a fresh, separate read of the same
pinned CRM database. Its code must identify exactly one row, its published flag
must equal 1, and its VIN must be present. The operation's immutable code/VIN must
match that read. Existing pinned identities cannot be reassigned. New cars do
not require configuration rewrites or fresh per-car approvals.

Instead of per-car `surfaces`, v2 requires `surface_templates`, containing every
served CARD, CATALOG and HOME location. Each has exactly `kind`, `path`, `url`
and boolean `price_applicable`. CARD path and URL each contain one
`{auto_number}` placeholder; other paths contain none. Substitution occurs only
for a separately verified CRM identity. All original root, origin, basename and
symlink protections apply. `price_applicable` must be true for CARD/CATALOG.
For a reviewed HOME containing only stage tiles or a redirect, it can explicitly
be false; the runtime then preserves and verifies its entire content. Missing
applicability is an error, never inferred clearance.

`operator_policy` has exactly:

```json
{
  "source": "AUTHENTICATED_TELEGRAM_UPDATE",
  "permission": "EXISTING_CRM_EDIT_CAR_ACL",
  "chat_types": ["private"],
  "roles": ["owner", "admin", "manager"]
}
```

The displayed private-chat scope is an example, not observed production policy.
Any existing authorized group workflow needs its actual `group`/`supergroup`
scope explicitly included in the reviewed delegation. Owner incident routing
keeps its independently verified private-chat evidence; successful operation
receipts use the authenticated originating operator/chat.

The actual pinned CRM adapter must perform its existing edit permission check
and persist factual `provenance_json` from the authenticated Update, with
`source: TELEGRAM_UPDATE`, `actor_id`, `chat_id`, `chat_type`, `bot_id`,
`message_id`, `update_id`, `authorized_car_id`, and `permission: EDIT_CAR`.
These fields are an audit record of that check, not permission granted by writing
a JSON flag. The provider independently rereads the exact durable v5 operation,
requires a current CLAIMED/DB_COMMITTED/SITE_PUBLISHED/VERIFIED checkpoint, and checks its
provenance, current bot, vehicle and configured chat scope. A private chat must
belong to the actor; group IDs must be negative. A synthetic source is accepted
only under an explicitly injected TEST root, and rejected by production.

The current captured `team_bot.who` admits active records from `db.get_staff`;
the observed roles are `owner`, `admin`, `manager`. The v2 provider independently
checks the same staff record is still active with one of those exact roles before
each authorization. It also requires installed code pins for `team_bot.py` and
the new confirmation module, in addition to the original complete dependency
set. Missing or revoked staff access cannot be replaced by provenance flags.

`Binding.resolve_identity(car_id)` supplies the dynamic verifier to `V5Worker`.
The resulting authority record binds the operation sequence, event hash,
operator evidence hash and originating operator/chat alongside the unchanged
canonical deployment chain. Local tests do not create any live anchor, receipt,
operator permission evidence or continuous control bridge.


## Owner clarification: publication-independent data guarantees (2026-09-20)

The owner requires the same data preservation, recovery and operator-change
protection for published and unpublished CRM records. Public visibility remains
controlled by publication status. The fixed-18 table above describes the legacy
v1 contract; current V5 uses a dynamic published set.

The normative clarification and required transition acceptance cases are in
[STATUS_INDEPENDENT_DATA_POLICY_RU.md](../task088_v5_acceptance/publication_status_policy_20260920/STATUS_INDEPENDENT_DATA_POLICY_RU.md).
Its implementation status is **OPEN**: the draft Stage 2 path, V5 operation
ledger and whole-page generation guard are not yet compatible across every
publication-status transition. See PS-01 and PS-02 in the linked policy.

This clarification does not remove existing published-only public-surface
checks, widen operator ACLs, alter the current delegation schema, or authorize
automatic first publication. A reviewed compatible implementation and exact
candidate acceptance are required before those transition guarantees can be
claimed. Historical evidence retains its original scope.
