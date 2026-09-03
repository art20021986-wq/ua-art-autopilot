# UA ART — MANUAL EXECUTION MODE

STATUS: ACTIVE
ACTIVATED_AT_UTC: 2026-09-03
OWNER_REASON: Four-day autopilot rehabilitation trial did not deliver a production-ready end-to-end execution pipeline.

## Operational rules

1. New task files do not automatically start Claude.
2. Autopilot fallback scheduling is disabled.
3. Every working task is executed through an explicit, human-controlled run.
4. Site health is checked before and after any production change.
5. Backup and rollback are mandatory for production writes.
6. CRM, VIN, prices, vehicle data and media are changed only within the approved task scope.
7. Workflow success or report creation is not TASK FINISHED; the requested result must be verified in the target environment.
8. Automatic mode may be restored only after a separate isolated test proves exact task routing, end-to-end execution, live verification and rollback without owner intervention.

SITE STATUS AT TRANSITION: Owner previously confirmed Safari, Chrome and TikTok access restored.
TASK107 STATUS AT TRANSITION: Routing/report stage completed; full executable optimization not implemented or verified.
