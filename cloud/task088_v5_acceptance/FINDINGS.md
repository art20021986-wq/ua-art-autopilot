# Remaining static findings against FINAL v5.0

Scope: the older candidate in `cloud/task088_price_sync` and its companion policy.
This audit is read only and does not establish current live installation status.
The source hashes for the candidate are in `observed_candidate.json`.

| v5 criterion | Source evidence | Practical consequence |
| --- | --- | --- |
| Separate processing across cars (§16, §27) | `uaart_price_sync_runtime.py`, `Worker.tick`: one publication lock encloses the whole claim/execute cycle. `_execute` holds `BEGIN IMMEDIATE` through file publication and HTTP readbacks. `register` uses `max_instances: 1`. | Different cars cannot process concurrently; unrelated DB writes also wait during network verification. A short lock for the shared catalog is still necessary, but the candidate serializes the entire operation. |
| Future cards work automatically (§9, §24) | `uaart_price_sync_binding.py`, `Provider._validate_delegation`: exactly 18 identity pairs and codes UA-0001 through UA-0018. Runtime `_identity` rejects anything outside the pinned map. | Future published cars cannot use this fixed price-sync binding without technical reconfiguration. |
| Complete operation history (§14) | `outbox.py`, `_DDL`: actor, selected market, old values and audit-row references are absent. `patch_cars_ui.py` hashes actor/field into the event key but does not store their relationship to the baseline audit rows. | The existing audit knows actor/market/old/new, while the outbox knows operation/revision/sync result; their required durable operation-level relationship is missing. This is not a claim that existing audit data has been deleted. |
| Operator completion receipt (§15) | Runtime `_NOTICE_DDL` allows only `FAILURE`, `DELAY`, `LATE`, `DAILY`; all sender calls use `binding.owner_chat_id`. Companion `owner_policy.py` excludes `COMPLETED` from `_NOTIFIABLE`. | The policy and sender must follow v5 completion receipts and operator routing. The executable success case already fails because it produces no notice. |
| Automatic restart (§17) | Runtime `_interruptions` makes claimed work STOPPED; `recover` requires a caller-supplied evidence builder. No automatic recovery caller is registered by `register`. | The recovery primitive alone does not implement restart recovery. Existing safe reconciliation and no-duplicate protections should be retained. |
| Permanent UA/GE PRICE PROTECTION (§26) | The inspected candidate tests are local suites. They do not themselves install an obligatory project-wide pre-Production check. | Live protection and every relevant production entrypoint need separate verification. This is an unestablished gate, not proof of present live absence. |

The companion `price_captions.py` is also an older RU/UA-only source with
AUTOPAPA/customs wording. The active renderer's exact RU/UA/GE captions and Rustavi
text belong in the Stage 3 audit; do not infer rendered output from this unused
helper alone.

Existing tests passed before this diagnostic: 136 price-sync tests and 55
owner-policy tests. Those passing tests do not supersede the demonstrated v5
failures. Independent DB read-back, source pinning, semantic price verification,
price-only byte preservation, recovery evidence and compare-and-swap rollback
are useful existing protections and should be preserved during correction.
