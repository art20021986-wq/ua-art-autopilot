# Handoff v4: точный допуск final17 v3

9 сентября 2026 UTC. Готовность остаётся **BLOCKED_BEFORE_EXACT_EXECUTION_PLAN**.

`code_handoff_v4.py` принимает новый final17 v3 с исправлением состояния отменённого CRM-редактора. В установщике заменены ровно три строковых значения: SHA application manifest, schema handoff и `candidate_id`. Все остальные байты исходника совпадают с `code_handoff_v3.py`. Алгоритмы проверки полномочий и квоты, удержания шести locks, backup, условной установки, journal, rollback и terminal readback сохранены.

| Артефакт | SHA-256 |
| --- | --- |
| Application final17 v3 manifest | `14f42086fc8bc94aefc4e4c83bda50e01107c30d2ad893c00d658f60d0c64fff` |
| `code_handoff_v4.py` | `0dec7fa5509da16b143698cee2a2ff5641385644c2f1ae01724fe516cce82000` |
| Новый `cars_ui.py` | `57ad5acc340d412aa9d95e1ef56c7de85d4346ad6bbc755fda311763f3637a42` |
| Локальный targeted result | `16a89d5623f7043c7b118a6ceb5e19e350293963cb5334e5bcabbdc3b2486863` |

Application manifest имеет `candidate_id: UA-ART-SPEC-AUTO10-COMPLETE-17-V3`; schema установщика — `UA-ART-COMPLETE17-CODE-HANDOFF-4`. Номера пакета приложения и установщика различны намеренно. В application-пакете изменён только `cars_ui.py`: прежний SHA `32dfec40ca2e6badfab222fd811fa710c52708fc0ff6bad80cbce79c0df5a0ec`; остальные 16 файлов и три execution dependency pin сохранены точно. Исходники и свидетельства v3 сохранены; v3 продолжает принимать только старый application v2 manifest `12afce821b784771a2a8a0415cc289f5e713d53aabedf0ed3e2747a8c4d4e136`.

## Доказательства и их предел

Фактический PythonAnywhere handoff v3 **30/30 PASS, 11:03:15 UTC**, остаётся свидетельством неизменённого алгоритма. Точный `evidence/handoff-v3-server-result.json`, SHA `d4de16383b4b5afba0bebb6cd16e7d1bb13c51f98bb9967cad7f61a0401e2fe2`, относится к синтетическим файлам и подставному authority. Эти 30 проверок повторно не запускались ради номера версии. Это не серверный запуск v4.

Новый `verify_handoff_v4_candidate.py` завершился локально **PASS в 12:00:10 UTC**. Протокол: `evidence/handoff-v4-actual17-local-result.json`. Проверено:

- побайтовое равенство алгоритма после трёх явно разрешённых замен;
- настоящий final17 v3 manifest без подмены admission pin, точный набор и compile всех 17 модулей; взаимный отказ v3/v4 для чужого manifest;
- единственная разница application bytes в `cars_ui.py`, неизменность остальных 16 файлов и трёх dependencies;
- один завершённый цикл установки настоящих 17 candidate bytes и явного rollback в новом временном каталоге с terminal readback через новый экземпляр `CodeHandoff`;
- возврат hash, mode и mtime 13 исходных fixture-файлов и отсутствия остальных четырёх, удержание шести fixture locks до финального readback;
- обязательные фазы authority, включая каждый из 17 install/rollback write; нулевое число запрещённых network, subprocess и production-access попыток; исходные inputs неизменны.

Legacy fixture bytes, authority, quota и session в этом сценарии **синтетические**. Настоящими являются новый application payload, manifest и dependency bytes. Исторические live SHA не выдаются за использованные fixture preconditions. CRM/site/worker модули не импортировались, production не изменялся, `overall_gate_b` остаётся `NOT_EVALUATED`, `unpause_authorized` — false.

Первая локальная попытка сохранена отдельно в `evidence/handoff-v4-actual17-local-harness-attempt1.json`: после установки assertion самого harness сравнил frozen disk receipt с mapping, изменённым последующим `read_terminal()` того же экземпляра. В существующем v3/v4 `_terminal` возвращает ссылку на `self.proof_digests`, и следующая проверка этого же объекта дописывает туда digest. Harness приведён к уже проверенному в v3 тестах образцу: terminal receipt читает новый экземпляр `CodeHandoff`. Алгоритм установщика не менялся; первая попытка не считается завершённым rollback-циклом. Временный fixture той попытки удалён штатной очисткой.

## Следующий подготовленный план

`prepare_maintenance_v3.py` создал отдельный `evidence/maintenance-v3-live17-handoff-v4-readiness.json`, readiness SHA `dac7d3874728e2b3b4d779dbd1e6da187e2cac3a4cbf938af704be1c4004fe6d`. Он связывает exact v4 source pin, новый application manifest, историческое серверное свидетельство v3 и новое локальное свидетельство v4; области доказательств подписаны отдельно.

В readiness использован неизменённый `evidence/live17-preconditions-20260909.json`: 13 присутствующих файлов и 4 явно отсутствующих на **10:54:07 UTC**. Это наблюдение, которое необходимо перечитать перед настоящей операцией. Свежие main/run/nonce/epoch и execution plan не назначены. Состояние webapp enabled, свежие dependency hashes, квота и pause/drain требуют независимого подтверждения.

Настоящий `verify_window` и полное доказательство завершения прежних WSGI/cron/manual writers остаются не реализованы. Локальный PASS не создаёт их. `owner_command` остаётся null; main, HALT, live tasks, production files, credentials и API этим этапом не изменяются. Когда настоящий проверенный маршрут и точный исполняемый план будут готовы, потребуется предусмотренная маршрутом отдельная команда владельца для точного плана. До этого готовность заблокирована, задачи автоматически не возобновляются.
