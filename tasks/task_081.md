# TASK 081 — UA-0013-PUBLISH-REPAIR-001 v1.0

## Команда владельца

29.08.2026 владелец потребовал: автоматически разобраться, почему автомобили не публикуются, немедленно поставить правильный этап, исправить критическую ошибку для UA-0013 и исключить повторение для будущих карточек.

Скриншот CRM в 14:14 показывает точный конфликт:
- `Публикация отменена: сборщик не смог собрать UA-0013 (SEO068_DIAGNOSTIC_TARGET_MISSING:UA-0013). Старая страница цела.`
- следующим отдельным сообщением: `Машина видна клиентам в каталоге.`

Публичная проверка в тот же момент: `/video/katalog.html` содержит 10 карточек и не содержит UA-0013. Следовательно, success CRM ложный.

## Режим

`BACKUP → fresh GET-only LIVE AUDIT → SANDBOX/CANARY → GATE A`.
Production/CRM/site writes и restart запрещены в этом task. Не заявлять live-fix до отдельного Gate B.
Продолжить и объединить TASK 073, TASK 077 и TASK 079; не создавать второй publisher или второй ETA writer.

## Доказанная первичная причина

1. В active `cars_ui.toggle_publish` сначала пишется `published=1`, затем вызывается `publikaciya.opublikovat`, но результат `_ok_rem2` не проверяется. После exception/failure handler безусловно отправляет success.
2. Active `_ua_seo068_normalize` в generators проверяет существование `UA-NNNN-diag.html` в live roots ДО того, как нижележащий publisher может создать diagnostic placeholder. Для новой карточки это делает failsafe недостижимым.
3. Нужен свежий live audit: после UA-0013 могли измениться SHA, DB row и active call path.

## Обязательный свежий GET-only аудит

Через PythonAnywhere API использовать только GET. Скачать во временную папку runner актуальные:
- `crm.db` + optional WAL;
- `cars_ui.py`, `publikaciya.py`, `stranica.py`, `master_card.py`, `yadro.py`, `cars_schema.py`, `db.py`;
- оба `katalog.html`;
- если существуют, primary/diag UA-0013 в `/video` и `/site`.

Зафиксировать без секретов:
- full SHA и exact AST definitions активных `toggle_publish`, `opublikovat`, `sobrat_kartochku`, `_ua_seo068_normalize`, ensure-diag helpers;
- ровно одну строку DB `auto_number=UA-0013`: id, published, publish_pending, review_status, status, container/date/ETA fields, required-field completeness, media counts;
- динамические status mappings and public category mapping;
- public HTTP status/occurrence UA-0013 in primary, diag, both catalogs.
Production touched = false.

## Правильный этап UA-0013

Не угадывать и не hardcode. Определить из свежей строки и утверждённой логики:
- terminal/Georgia/Kyiv statuses никогда не откатывать;
- если есть подтверждённые контейнерные признаки, канонический ferry status = `sea_loaded`, label/badge = `На пароме`, category = `more`;
- если контейнерных признаков нет и текущий статус Korea-family, сохранить/нормализовать только к активному каноническому Korea status и category `korea`;
- status, CRM label, page badge и catalog category должны совпасть.
Любая неоднозначность = fail closed с точным evidence, без записи.

## Системное исправление для UA-0013 и всех будущих карточек

1. Diagnostic page/placeholder `Материалы диагностики ожидаются` создаётся внутри staging bundle ДО SEO normalization/validation. Отсутствующая диагностика не блокирует новую карточку.
2. Не ослаблять проверку wrong diagnostic link: primary обязан ссылаться ровно на свой `UA-0013-diag.html`.
3. Publisher строит во временном каталоге полный bounded bundle: primary + diag/placeholder + `/video/katalog.html` + `/site/katalog.html`; compile/validate, unique identifier, exact href, stage/category, required content; затем atomic install/read-back.
4. `toggle_publish` сохраняет exact `published` preimage. Если для сборки требуется временно `published=1`, при любом publisher/build/install/verify FAIL выполнить compensating DB rollback и проверить preimage. Success разрешён только когда `ok is True`, primary+diag доступны и UA-0013 ровно один раз присутствует в обоих каталогах.
5. Ровно одно итоговое сообщение: PASS — только `Машина видна клиентам в каталоге.`; FAIL — только понятная причина. Нельзя сначала failure, потом success.
6. `published`, `status`, `publish_pending` после failure совпадают с preimage.
7. После PASS correct stage and catalog category совпадают; карточка сохраняет фото, видео, VIN, цену, описание.
8. Никакого synthetic HTML и полной перегенерации дизайна. Использовать active master template/generator.
9. Fix generic для любого `UA-[0-9]{4,}`, не hardcode UA-0013.
10. Runtime LLM tokens = 0.

## Sandbox/canary

На свежей копии production:
- воспроизвести текущий FAIL UA-0013;
- после candidate UA-0013 без диагностики получает placeholder и полный bundle;
- future UA-9999 без диагностики проходит тот же путь;
- publisher injected FAIL/exception/read-back mismatch/partial install/delayed overwrite → rollback and exactly one failure message;
- PASS → exactly one success message;
- two deterministic runs;
- dynamically проверить все текущие cards, отдельно UA-0009, UA-0012, UA-0013;
- protected existing primary/media hashes unchanged; catalogs change only expected one-card insertion;
- no duplicate card, CTA, diag link or category.

## Release tooling

Создать полный исполнимый комплект под `cloud/task_081_publish_repair/`:
- `live_probe.py` и sanitized evidence/report;
- deterministic AST/full-SHA anchored `patcher.py`;
- `installer.py`, `controller.py`, `postcheck.py`;
- tests и sandbox report;
- `gate_a_workflow.yml` (GET-only, допускается push-trigger только для своего пути);
- `gate_b_workflow.yml` только `workflow_dispatch`, exact token:
  `UA-0013-PUBLISH-REPAIR-001-V1.0-PRODUCTION-APPROVED`;
- backup/atomic install/auto-rollback, exclusive production concurrency, restart exact active launcher only after install;
- postcheck immediate + delayed: UA-0013 HTTP 200, diag HTTP 200, exactly one occurrence in both catalogs, correct stage/category, all protected hashes unchanged.

Gate A итог только:
- `PASS_READY_FOR_SEPARATE_PRODUCTION_APPROVAL`, либо
- точный fail-closed blocker.

Обновить `cloud/latest_status.md` и `cloud/owner_reply.md`.
