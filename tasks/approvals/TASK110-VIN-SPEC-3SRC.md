# TASK110 production approval

TASK_ID: TASK110-VIN-SPEC-3SRC
STATUS: OWNER_APPROVED
TASK_CLASS: CRITICAL
SCOPE: VIN-triggered additional specification for all existing and future UA ART cards
GATE_B: AUTHORIZED
PRODUCTION_WRITE: AUTHORIZED_FOR_THIS_TASK_ONLY
MAIN_CRM_WRITE: FORBIDDEN
ADDITIONAL_SPEC_SIDECAR_WRITE: AUTHORIZED
PUBLISHED_EXISTING_CARD_REFRESH: AUTHORIZED
INITIAL_AUTOPUBLICATION: FORBIDDEN
PRIMARY_FIELDS_AND_PRICES: FORBIDDEN
MEDIA_WRITE: FORBIDDEN
GLOBAL_AUTOMATIC_MODE: UNCHANGED
BACKUP: REQUIRED
rollback: REQUIRED_AND_AUTOMATIC_ON_FAILURE

Owner instruction recorded on 2026-09-04: preserve the familiar CRM flow in
which a valid VIN opens a new card; automatically collect the additional
specification and send it to the dedicated block on all old and future cards.
Audit the source list and keep only the useful sources; up to five sources are
allowed if genuinely needed. This approval is bounded to TASK110.

УТВЕРЖДАЮ ПРОДОЛЖЕНИЕ UA-ART-FAST-PIPELINE-001 ДО ПОЛНОГО TASK FINISHED
