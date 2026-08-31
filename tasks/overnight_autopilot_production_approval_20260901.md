# UA ART — Overnight Autopilot Production Authorization

OWNER_APPROVED: YES
OVERNIGHT_PRODUCTION_AUTHORIZED: YES
REQUIRE_BACKUP: YES
REQUIRE_SANDBOX_PASS: YES
REQUIRE_CANARY_PASS: YES
REQUIRE_SAFETY_PASS: YES
AUTO_REPAIR_RETRY: YES
ROLLBACK_ON_FAILED_GATE: YES
BUSINESS_COMPLETE_REQUIRED: YES
STOP_ONLY_ON_BUSINESS_COMPLETE_OR_OWNER_ONLY_ACTION: YES

Owner instruction:

> УТВЕРЖДАЮ НОЧНОЙ AUTOPILOT PRODUCTION. После обязательных BACKUP → SANDBOX PASS → CANARY PASS → SAFETY PASS разрешаю автономно довести ранее утверждённые ТЗ сайта и CRM до Production и BUSINESS_COMPLETE. При любой ошибке — автоматический repair/retry либо rollback. Не публиковать ничего, что не прошло проверки. Остановиться только при BUSINESS_COMPLETE либо если физически требуется моё действие/2FA.

Scope: previously owner-approved UA ART site and CRM work only. This authorization does not waive safety gates, validation, backups, canary checks, or rollback requirements. Unapproved new functionality remains out of scope.
