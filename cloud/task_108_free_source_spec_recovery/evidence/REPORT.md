# TASK108 — отчёт canary без платного API

STATUS: **CANARY_PASS_LIVE_REMEDIATION_REQUIRED**

Production: **не разрешён и не затронут**. Live CRM write: **NO**. Public path write: **NO**. Service restart: **NO**. Autopublication: **NO**.

## Canary

| Карточка | Статус | Identity score | Принято фактов | Карантин/отклонено |
|---|---:|---:|---:|---:|
| UA-0005 | READY_FOR_OPERATOR_REVIEW | 1.00 | 13 | 1 |
| UA-0015 | REVIEW_REQUIRED_EXACT_TRIM | 1.00 | 6 | 4 |

UA-0005 прошла структурный canary и готова только к просмотру оператором. UA-0015 имеет безопасное превью, но остаётся `REVIEW_REQUIRED_EXACT_TRIM`: бесплатный NHTSA-декодер вернул критические ошибки, а точная модификация taxi/rental по VIN не подтверждена.

## Подготовленные карточки

| Карточка | Статус | Подтверждено фактов | Категорий |
|---|---:|---:|---:|
| UA-0001 | READY_FOR_OPERATOR_REVIEW | 10 | 5 |
| UA-0002 | READY_FOR_OPERATOR_REVIEW | 22 | 7 |
| UA-0003 | REVIEW_REQUIRED_EXACT_TRIM | 5 | 2 |
| UA-0004 | REVIEW_REQUIRED_EXACT_TRIM | 5 | 2 |
| UA-0005 | READY_FOR_OPERATOR_REVIEW | 13 | 6 |
| UA-0006 | REVIEW_REQUIRED_EXACT_TRIM | 5 | 2 |
| UA-0007 | READY_FOR_OPERATOR_REVIEW | 22 | 7 |
| UA-0008 | READY_FOR_OPERATOR_REVIEW | 22 | 7 |
| UA-0009 | REVIEW_REQUIRED_EXACT_TRIM | 6 | 3 |
| UA-0010 | REVIEW_REQUIRED_EXACT_TRIM | 6 | 3 |
| UA-0011 | REVIEW_REQUIRED_EXACT_TRIM | 6 | 3 |
| UA-0012 | REVIEW_REQUIRED_OPERATOR_FIELDS | 6 | 3 |
| UA-0013 | REVIEW_REQUIRED_OPERATOR_FIELDS | 19 | 8 |
| UA-0015 | REVIEW_REQUIRED_EXACT_TRIM | 6 | 3 |

Три W245 (UA-0002, UA-0007 и UA-0008) привязаны к заводскому типу `245.232` по общему VIN-префиксу и получили по 22 одинаково проверенных технических параметра. Маркетинговое имя 2009 года не угадывается: привязка сделана к заводскому типу.

## Строгие проверки

- PASS — `all_16_cards_snapshotted`
- PASS — `protected_fields_unchanged`
- PASS — `no_protected_code_accepted`
- PASS — `no_empty_card_passed`
- PASS — `no_semantic_duplicate_rendered`
- PASS — `server_rendered_details_present`
- PASS — `json_ld_present`
- PASS — `mobile_wrap_rules_present`
- PASS — `source_urls_not_public`
- PASS — `production_touched_false`
- PASS — `autopublication_false`
- PASS — `all_bundles_target_known_cards`
- PASS — `source_policy_valid`
- PASS — `operator_review_queue_valid`
- PASS — `operator_review_cards_blocked`
- PASS — `ten_identical_runs`

## Доказательство неизменности

- BEFORE protected fields SHA-256: `eda47234ac44e93f2509bc6edb711aa2c4bc26a27497b7b11e8d76955d283c37`
- AFTER protected fields SHA-256: `eda47234ac44e93f2509bc6edb711aa2c4bc26a27497b7b11e8d76955d283c37`
- Совпадение: **PASS**
- 10 идентичных запусков: **PASS**

## Исправленная логика

- Ноль подтверждённых фактов теперь означает только `REVIEW_REQUIRED_EMPTY`, никогда не PASS.
- Смысловой код уникален; повторяющиеся «Высота», «Длина» и другие дубли не попадают в HTML.
- Конфликты не усредняются. Для UA-0005 из выдачи исключена максимальная скорость; для UA-0015 исключены высота, расход, масса и CO₂.
- Публичный блок не содержит URL источников, но происхождение каждого факта сохраняется во внутреннем evidence.
- URL сам по себе не считается доказательством: каждый источник обязан иметь проверенный JSON-снимок утверждений с SHA-256, а код/значение/единица/примечание должны совпасть точно.
- Источник, который отвечает блокировкой или не имеет проверяемого снимка, не участвует в обогащении.
- HTML и JSON-LD сформированы на сервере; JavaScript для индексации не нужен.

## Live-аудит 16 карточек

- Статус: **FAIL** — пока блокирует Production.
- Проверено карточек: **16**.
- Пустая спецификация: **15** карточек.
- Пустой HTML-блок больше не считается наличием спецификации и не может дать общий PASS.
- Служебные подсказки оператора CRM удаляются только по точным публично недопустимым шаблонам.

## Полный парк

В Sandbox подготовлены подтверждённые наборы для **14 из 16** карточек. TASK108 не выдаёт фиктивный общий PASS. Карточек без нового проверенного набора фактов: **2** (UA-0014, UA-0016); они остаются `REVIEW_REQUIRED_EMPTY`. UA-0012, UA-0013, UA-0014 и UA-0016 имеют операторские значения, требующие проверки; TASK108 их фиксирует в аудите, но не меняет.

## Очередь проверки полей CRM

| Карточка | Поле | Текущее значение | Причина остановки |
|---|---|---:|---|
| UA-0012 | `mileage_km` | `342` | `MILEAGE_342_REQUIRES_CONFIRMATION` |
| UA-0013 | `year` | `2015` | `YEAR_2015_CONFLICTS_WITH_VIN_MODEL_YEAR_2016` |
| UA-0014 | `engine_cc` | `1645` | `ENGINE_CC_1645_REQUIRES_CONFIRMATION` |
| UA-0016 | `year` | `1999` | `YEAR_1999_REQUIRES_CONFIRMATION` |
| UA-0016 | `mileage_km` | `353` | `MILEAGE_353_REQUIRES_CONFIRMATION` |

Очередь доступна только для чтения: она сохраняет точные текущие значения CRM, не содержит предлагаемой замены и не даёт права на запись. Ошибок целостности очереди: **0**.

UA-0009 PUBLICATION READINESS: **FAIL**

SAFE TO PUBLISH UA-0009: **NO**

SAFE TO PUBLISH ANYTHING: **NO**

## Следующий разрешённый шаг

Получить ручное подтверждение отмеченных полей для UA-0012, UA-0013, UA-0014 и UA-0016 и точных модификаций карточек со статусом `REVIEW_REQUIRED_EXACT_TRIM`. Любое Production-применение остаётся отдельным шлюзом после итогового отчёта и резервного копирования.
