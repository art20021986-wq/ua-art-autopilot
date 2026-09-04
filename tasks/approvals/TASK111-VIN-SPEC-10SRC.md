# TASK111 production approval

TASK_ID: TASK111-VIN-SPEC-10SRC
STATUS: OWNER_APPROVED
TASK_CLASS: CRITICAL
SCOPE: TEN-SOURCE VIN ADDITIONAL SPECIFICATION FOR ALL EXISTING AND FUTURE UA ART CARDS
GATE_B: AUTHORIZED
PRODUCTION_WRITE: AUTHORIZED_FOR_THIS_TASK_ONLY
MAIN_CRM_WRITE: FORBIDDEN
ADDITIONAL_SPEC_SIDECAR_WRITE: AUTHORIZED
ALL_EXISTING_CARD_BACKFILL: AUTHORIZED
PUBLISHED_EXISTING_CARD_REFRESH: AUTHORIZED
VIN_ENRICHMENT_AUTOSTART: AUTHORIZED
INITIAL_AUTOPUBLICATION: FORBIDDEN
PRIMARY_FIELDS_AND_PRICES: FORBIDDEN
MEDIA_WRITE: FORBIDDEN
GLOBAL_AUTOMATIC_MODE: UNCHANGED
BACKUP: REQUIRED
ROLLBACK (rollback): REQUIRED_AND_AUTOMATIC_ON_FAILURE

Owner instruction recorded on 2026-09-04: the result of two populated cards out
of fourteen is unacceptable. Restore the ten-source plan, maximize additional
technical information for every car, complete all old cards, and keep the
process automatically active for all new cards. This approval is bounded to
TASK111 and does not authorize changing primary CRM fields, prices, initial
publication behavior, media, DNS, or global manual mode.

УТВЕРЖДАЮ ПРОДОЛЖЕНИЕ UA-ART-FAST-PIPELINE-001 ДО ПОЛНОГО TASK FINISHED
