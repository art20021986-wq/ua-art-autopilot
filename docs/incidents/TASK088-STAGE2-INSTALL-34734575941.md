# Stage 2 install incident: factual reconciliation draft

The approved `cars_ui.py` source is installed on disk, according to the authenticated PythonAnywhere readback reported at 05:17 UTC on 13 September 2026. Its SHA-256 is `4c00512c56ee19ccda4ff0086aa696facf8aeea013c894168007c78c9490adde`, exactly the approved candidate.

The run-specific remote verification result was read at 05:19 UTC. It records `INSTALLATION_VERIFIED` at 03:16:31.774779 UTC: database unchanged, 19 CRM records, integrity PASS, protected sources unchanged, no migration, no live-price writes and no site writes. Backup and rollback are ready. It explicitly records `bot_restart=NOT_PERFORMED` and `code_activation=PENDING_RESTART`.

Stage 2 has not passed acceptance. The bot has not been activated with the new code by this installation. Telegram acceptance remains pending.

## What failed

[Run 34734575941](https://github.com/art20021986-wq/ua-art-autopilot/actions/runs/34734575941) completed backup and the production controller. At 03:16:54 UTC the controller reported `FINISHED` only for `INSTALLATION_AND_SOURCE_DB_READONLY_VERIFY`, with `PENDING_TELEGRAM_CHECKS`.

The launch ledger expired at 03:15:40 UTC. At 03:17:13 the finalizer rejected it with `AUTOSTART_LEDGER_EXPIRED` before persisting the receipt.

The workflow reserved its one automatic rollback attempt. The rollback preflight then failed at 03:17:34 with `AUTOSTART_NONCE_RESERVATION_MISSING`, wrapped as `TRANSACTION_LEDGER_INVALID`. The reservation exists on main. The critical workflow reconstructs a checkout pinned to the earlier source commit and copies five durable records, but omits the nonce reservation created after that commit. Consequently the rollback controller did not execute.

Current recorded state at main commit `b8e2f3ce1f8fc77f12cec04776ce4dc53994a78a`: transaction `ROLLING_BACK`, claim `BLOCKED_ROOT_CAUSE`, `EMERGENCY_HALT`. The halt explicitly states rollback performed false.

## Existing recovery rules

The opening contract in `automation/transaction_watchdog.py` says that `ROLLING_BACK` consumes the one automatic rollback attempt and requires manual reconciliation. This rule does not itself demand a new owner phrase.

The watchdog workflow states that a valid same-epoch HALT blocks forward work, not recovery. Existing owner authorization therefore supports further factual diagnosis and preparation of exact recovery. It does not justify bypassing state validation.

There is no implemented generic forward-only `accept-installed` reconciliation command. `close_production_transaction` permits `FINISHED` only from `OPEN` and `ROLLED_BACK` only from `ROLLING_BACK`. Neither falsely declaring rollback nor resetting this transaction to OPEN is valid.

The existing explicit HALT-release command is bound to `UA-ART-RECOVERY-TASK120-002` and fixed TASK120 identities. It cannot be reused for TASK088, and its separate owner-phrase requirement should not be misrepresented as a generic requirement for all manual reconciliation.

## Required continuation

Cross-check the remote backup and execute results against the already-read historical verify result and check their bindings against this exact request/run/transaction. Confirm the active CRM process loaded the approved source. Preserve the actual outcome in an incident-specific reviewed reconciliation route before any transaction/HALT release or further forward production execution. Complete the actual Telegram checks, separate DB readbacks and original-value restoration before parent Stage 2 PASS.

Do not extend consumed expiry, reset rollback state, rerun the reserved automatic rollback, reuse TASK120 release identity, or treat the installation-only controller result as full Stage 2 acceptance.

This branch adds evidence only: no application, runtime, HALT, transaction, nonce or launch changes. The companion JSON distinguishes direct GitHub observations from parent-agent server observations and records remaining evidence gaps.
