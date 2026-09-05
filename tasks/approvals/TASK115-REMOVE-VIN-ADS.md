# TASK115 production approval

TASK_ID: TASK115-REMOVE-VIN-ADS
STATUS: OWNER_APPROVED
TASK_CLASS: CRITICAL
SCOPE: Remove unsolicited VIN advertising from all public cards, restore additional specification, disable autonomous VIN enrichment, and block unapproved external domains in future card publications
GATE_B: AUTHORIZED
PRODUCTION_WRITE: AUTHORIZED_FOR_THIS_TASK_ONLY
CRM_DATA_WRITE: FORBIDDEN
MEDIA_WRITE: FORBIDDEN
VIN_VALUE_WRITE: FORBIDDEN
CARD_BUSINESS_DATA_WRITE: FORBIDDEN
BACKUP: REQUIRED
ROLLBACK: REQUIRED_AND_AUTOMATIC_ON_FAILURE

Owner instruction recorded on 2026-09-05: remove Korea CarHistory and the
"Проверить VIN" advertisement from the website, prevent any advertisement
from being inserted automatically without owner knowledge, restore the
additional specification, and continue the Ukrainian/Georgian/eight-country
project afterward.

УТВЕРЖДАЮ ПРОДОЛЖЕНИЕ UA-ART-FAST-PIPELINE-001 ДО ПОЛНОГО TASK FINISHED
