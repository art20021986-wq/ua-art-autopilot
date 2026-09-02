# TASK105 — Owner authorization for full completion

## Owner command

«УТВЕРЖДАЮ ПРОДОЛЖЕНИЕ UA-ART-FAST-PIPELINE-001 ДО ПОЛНОГО TASK FINISHED: FAST → STANDARD → CRITICAL → переключение основного маршрута; обязательные backup, live-проверка и автоматический rollback при любой ошибке. CRM и данные автомобилей не изменять без отдельной необходимости.»

Received from the owner on 2026-09-02.

## Authorized sequence

1. Complete additional FAST acceptance.
2. Run STANDARD sandbox and bounded production canaries.
3. Build and test the CRITICAL adapter while preserving strict approval, backup, canary and rollback gates.
4. Install the permanent FAST / STANDARD / CRITICAL routing workflows.
5. Switch new task intake to the central orchestrator only after all acceptance gates pass.
6. Keep legacy workflows available as rollback/fallback until parity is proven; no destructive deletion in this task.

## Hard safety requirements

- Every production write requires a verified preimage backup.
- Every production write requires immediate and delayed live verification.
- Any failed invariant must stop the current stage and invoke the verified rollback path.
- CRM database and vehicle records must remain byte-for-byte unchanged unless a later task explicitly requires and authorizes such a change.
- Existing homepage, catalog and vehicle media must remain unchanged during canary stages.
- Cloudflare and DNS are out of scope.
- No blind retries after logical or safety failures; use ROOT_CAUSE_MODE on the same TASK105.
- A stage may be called FINISHED only through a valid final receipt.
