# TASK 088 — OWNER-CURRENT-UA0011-KOREA-NOW-008 v1.0

## Прямая текущая команда владельца

Дата: 29.08.2026.

UA-0011 должна быть полноценно размещена только со статусом «В Корее»:
`status='kr_bought'`. Удалить её из «На пароме», «Грузия» и «Киев».
Сохранить VIN `KMHE341DBKA544289`, бизнес-информацию, диагностику, все фото и
главную фотографию `video/foto/UA-0011/m/001.jpg`.

Очистить несовместимый payload: `sea_container=NULL`,
`sea_date_out=NULL`, `sea_port_from=NULL`, `days_to_kyiv=NULL`,
`eta_manual=NULL` и поздние Georgia/Kyiv поля.

TASK 088 окончательно отменяет ferry-цель прежней TASK 086/087. Дополнительное
подтверждение владельца не требуется.

Пересобрать полную карточку, diagnostic companion и оба каталога. UA-0011
ровно один раз в `korea`; видимый Korea counter равен фактическому числу
уникальных карточек. Все chips пересчитывать из одного CRM snapshot с
инвариантом `all = korea + more + gruzia + kiev`.

Ввести постоянный cross-control: единый stage writer, SQLite triggers,
stage-aware public projection, atomic publisher, byte read-back, immediate и
delayed проверки. Два writer-процесса одновременно запрещены. Разрешён один
последовательный автоповтор. Любой сбой — compensating DB rollback, точное
восстановление файлов и restart единственного
`python3.10 /home/Carix/start_safe.py`. Runtime LLM tokens = 0.

PASS только после подтверждения базы, полной карточки с фото/VIN/диагностикой,
обоих каталогов, категорий, всех счётчиков, неизменности остальных строк/media
и delayed HTTP. Реализация: `cloud/task_085_stage_payload_reset/`.
