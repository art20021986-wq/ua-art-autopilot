# UA ART — MANUAL EXECUTION MODE

STATUS: INACTIVE
DEACTIVATED_AT_UTC: 2026-09-04T14:27:55Z
REPLACED_BY: state/EXECUTION_MODE.json
OWNER_COMMAND: Включай глобальный продакшн автопилот.

## Active operating mode

Global automatic intake is enabled for new exact launch markers created after
the activation timestamp. Automatic Production execution is allowed only when
the individual immutable request also carries the owner's approval, Gate A,
explicit Gate B authorization, backup/rollback requirements, target storage
probe, pre/post health checks and a validated live receipt.

Existing launch markers are never replayed. Any identity, safety, storage,
health, backup, rollback or receipt failure stops the exact task fail-closed.
