# TASK 106 — UA-ART-SITE-RECOVERY-GUARD-001

Priority: P0
Owner authorization: APPROVED 2026-09-02

Owner command:
«УТВЕРЖДАЮ UA-ART-SITE-RECOVERY-GUARD-001. P0. Восстановить и защитить сайт, проверить rollback, только после полного SITE HEALTH PASS продолжить UA-ART-FAST-PIPELINE-001.»

## Mandatory execution order
1. Freeze all feature/development production work.
2. Read-only health audit first: DNS/HTTPS/home/catalog/key card/CRM health/PythonAnywhere/public mobile-compatible endpoints.
3. Establish LAST_KNOWN_GOOD evidence and protected SHA baseline.
4. Build deployment guard in isolated branch/sandbox. No production write until deterministic tests PASS.
5. Guard must block all deploys when SITE_HEALTH != PASS.
6. Before any production write: backup + manifest + protected SHA.
7. Atomic production changes only.
8. Post-deploy live checks: http/https, www/non-www where applicable, home, catalog, representative card/static assets and CRM health without CRM mutation.
9. Any critical FAIL => freeze queue; rollback last bounded change; verify rollback.
10. DNS/Cloudflare/registrar changes are CRITICAL and are forbidden to normal FAST/STANDARD tasks.
11. CRM, VIN, prices, vehicle rows, photos and videos must not be mutated by recovery unless separately proven necessary and authorized.
12. Failure injection required: 404/500/502/503, DNS failure model, timeout, corrupt deploy, protected-file mutation, rollback verification.
13. UA-ART-FAST-PIPELINE-001 remains frozen until full SITE HEALTH PASS and recovery guard acceptance.

## Definition of done
DOMAIN PASS -> DNS PASS -> HTTPS PASS -> HOME PASS -> CATALOG PASS -> CAR PASS -> CRM HEALTH PASS -> MOBILE SAFARI COMPAT PASS -> BACKUP PASS -> ROLLBACK TEST PASS -> DEPLOY GUARD PASS -> SITE STABLE -> TASK FINISHED.

No intermediate PASS, workflow success, file creation or sandbox result may be called TASK FINISHED.
