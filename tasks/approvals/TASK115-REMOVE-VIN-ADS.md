# TASK115 production approval

TASK_ID: TASK115-REMOVE-VIN-ADS
STATUS: OWNER_APPROVED
TASK_CLASS: CRITICAL
SCOPE: Remove unsolicited VIN advertising from all public cards, restore additional specification, preserve and keep enabled the autonomous VIN specification worker, and block unapproved external domains in future card publications
SCHEDULER_QUARANTINE: IRREVERSIBLY_DELETE_ALL_ENABLED_AND_DISABLED_LEGACY_TASK068_DEFINITIONS
REMOTE_REINSTALLER_QUARANTINE: IRREVERSIBLY_DELETE_THREE_EXACT_LEGACY_VIN_AD_PAYLOADS
QUARANTINE_ROLLBACK_POLICY: NEVER_RESTORE_EITHER_OWNER_FORBIDDEN_QUARANTINE
GATE_B: AUTHORIZED
PRODUCTION_WRITE: AUTHORIZED_FOR_THIS_TASK_ONLY
CRM_DATA_WRITE: FORBIDDEN
MEDIA_WRITE: FORBIDDEN
VIN_VALUE_WRITE: FORBIDDEN
CARD_BUSINESS_DATA_WRITE: FORBIDDEN
BACKUP: REQUIRED
ROLLBACK: REQUIRED_AND_AUTOMATIC_ON_FAILURE_FOR_SEVEN_REVERSIBLE_TARGETS_ONLY; BOTH_QUARANTINES_RETAINED

Owner instruction recorded on 2026-09-05: remove Korea CarHistory and the
"Проверить VIN" advertisement from the website, prevent any advertisement
from being inserted automatically without owner knowledge, restore the
additional specification, keep its autonomous VIN specification worker enabled,
delete all enabled and disabled legacy TASK068 scheduler definitions and all
three declared remote VIN-ad reinstallers irreversibly, and continue the
Ukrainian/Georgian/eight-country project afterward. File rollback must never
restore either forbidden quarantine.

УТВЕРЖДАЮ ПРОДОЛЖЕНИЕ UA-ART-FAST-PIPELINE-001 ДО ПОЛНОГО TASK FINISHED
