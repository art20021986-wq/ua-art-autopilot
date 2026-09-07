# Latest status — TASK116

**Updated:** 2026-09-07 05:59 UTC  
**Contract:** `UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001` v1.0

- Candidate выполняется только в ветке
  `codex/ua-art-crm-spec-publish-recovery-001`.
- Production runtime/CRM/site/reload/publisher: изменений `0`.
- `UA-0017`: одна точная CRM-строка; VIN подтверждён по SHA-256
  `bdc6d48c3d19b41916729cb3c207518bb1db0f06a1fe95b23fa461f6f557709b`;
  `published=0`, `publish_pending=0`.
- Remote Gate A probe выполнен read-only. Он честно вернул `FAIL/UNKNOWN`, так
  как общий `/home/Carix` содержит 60 DB и 2333 HTML-кандидата, а его
  диагностические списки ограничены 32/512. Probe подтвердил отсутствие
  записей, reload и сетевых запросов.
- Авторитетные входы установлены отдельно read-only:
  `/home/Carix/crm.db`, `/home/Carix/vin_specs_task111_v3.db`,
  `/home/Carix/site`, `/home/Carix/video`.
- Получен fresh snapshot: две согласованные SQLite-копии и 1061 web-файл;
  ZIP SHA-256
  `b0b02613b2eaa4aa4ec1fa117c477415607a729c83d5057f3c5d4e967dc75a89`.
- Patcher успешно применён только к fresh-копии после адаптации к фактической
  active-форме `cars_ui.py`; изменены ровно 5 разрешённых runtime-файлов.
- Fresh snapshot compatibility: 11/11 PASS; обе DB `quick_check=ok`, 1061/1061
  web-файлов byte-for-byte неизменны, `UA-0017` не опубликована и не
  материализована.
- Локальная failure/rollback candidate-матрица: 14/14 PASS.
- Gate B: `NOT_ELIGIBLE`; Production gate: `CLOSED`.

Остаток до verified Gate B:

1. внешний trusted release-controller;
2. durable одноразовый owner nonce;
3. OS-level write allowlist;
4. crash-durable snapshot/recovery;
5. computed-CSS browser verification на изолированном preview.

Даже после Gate B выпуск допустим только по отдельной точной команде:

`ПУБЛИКОВАТЬ UA-0017`
