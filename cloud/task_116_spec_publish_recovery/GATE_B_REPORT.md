# TASK116 — Gate B report

**Contract:** `UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001` v1.0  
**Report date:** 2026-09-07  
**Gate B verdict:** `FRESH_SNAPSHOT_COMPATIBILITY PASS / NOT_ELIGIBLE`  
**Production gate:** `CLOSED`  
**UA-0017 release:** `BLOCKED`; **Production state:** `OBSERVED UNPUBLISHED`

## Executive result

Получен свежий remote-derived snapshot двух DB, фактического runtime и web-root
`/home/Carix/site` и `/home/Carix/video`. Compatibility-этап на его изолированной
копии завершён 11/11 PASS: обе DB `quick_check=ok`, точная `UA-0017` совпала по
VIN hash, patcher изменил ровно пять разрешённых runtime-файлов, а 1061 web-файл
остался byte-for-byte неизменным. Production URL, DB, runtime, service и
publisher не изменялись. Финальный Gate B всё ещё закрыт оставшимися системными
контролями; публиковать `UA-0017` запрещено.

Candidate фиксируется только в отдельной ветке
`codex/ua-art-crm-spec-publish-recovery-001`; exact head проверяется через
GitHub evidence. Production-root `/home/Carix` не используется как
доказательство branch/commit.

## Что действительно проверено локально

2026-09-07T04:44:17Z команда

```bash
PYTHONDONTWRITEBYTECODE=1 python3 sandbox_gate_b.py
```

завершила 14/14 локальных candidate-cases со статусом `PASS`. Runner сам
маркирует результат `B_LOCAL_CANDIDATE`, `PREVIEW_ONLY` и явно сообщает:
Remote Gate B не выполнялся. Свежий результат и candidate manifest сохранены в
`evidence/gate_b_local.json`, но он явно содержит `gate_b_eligible=false`,
`production_eligible=false` и `release_authorization=BLOCKED`; этот файл не
может открыть Production gate.

| Уровень | Фактический статус | Разрешает Production |
|---|---|---|
| Local candidate | 14/14 PASS, manifest-bound evidence | Нет |
| Remote Gate A | Probe FAIL/UNKNOWN из-за bounded inventory; exact paths bound read-only | Нет |
| Gate B на remote-derived копиях | Compatibility 11/11 PASS; final controls pending | Нет |
| Owner Production command | NOT_GIVEN_FOR_RELEASE | Нет |

Fresh snapshot ZIP имеет SHA-256
`b0b02613b2eaa4aa4ec1fa117c477415607a729c83d5057f3c5d4e967dc75a89`.
Для `UA-0017`: одна точная строка, `published=0`, `publish_pending=0`,
дополнительная спецификация `0/10`; неполная спецификация корректно оставляет
выпуск заблокированным. Evidence: `evidence/gate_b_fresh_snapshot.json`.

## Матрица A–F

| Этап | Локальное покрытие candidate | Требуемое удалённое доказательство | Статус Gate B |
|---|---|---|---|
| A — BEFORE/identity | Pure guards и synthetic identity tests | Фактические root/DB/runtime, GitHub branch/commit evidence, exact UID/VIN из CRM, `published` | NOT_RUN |
| B — дополнительная спецификация | Revision immutability, empty refresh, unrelated-change test | Старые и новые реальные карточки на свежей копии remote-state | NOT_RUN |
| C — основная спецификация | Empty-only CAS, decoder mismatch/outage, смена VIN с сохранением ручных данных | Реальная schema-copy и VIN hook | NOT_RUN |
| D — статусы CRM | Hidden status и stale callback tests | Фактические Telegram handlers/keyboard и history-copy | NOT_RUN |
| E — публикация | Preview atomicity, exact identity, fresh-source patcher | Обе реальные root-copy, каталог, диагностика, failure injection | NOT_RUN |
| F — rollback/release | Synthetic rollback tests | Восстановимый snapshot, kill-path план, canary и post-check | NOT_RUN |

## Обязательные блокеры до Gate B

Remote-derived snapshot и применение patcher к копии выполнены. Остались:

1. Установить внешний доверенный release-controller.
2. Добавить durable одноразовый owner nonce, связанный с exact UID/VIN,
   candidate commit и свежим Gate B receipt.
3. Включить OS-level write allowlist только для разрешённых target-артефактов.
4. Доказать crash-durable snapshot/restore при аварийном завершении процесса.
5. Выполнить computed-CSS browser-проверку на изолированном preview для старой,
   новой и целевой карточки.
6. Связать обновлённый candidate manifest и snapshot evidence с новым exact
   commit отдельной ветки.

## Требуемые read-only доказательства Gate A

Probe запускается без редиректа самим скриптом; stdout сохраняет внешний
контрольный контур:

```bash
python3 -B remote_gate_a.py \
  --root /home/Carix \
  --uid UA-0017 \
  --vin <EXACT_UA0017_CRM_VIN>
```

VIN в команде должен быть получен из единственной точной CRM-строки `UA-0017`;
VIN публичной `UA-0002` использовать запрещено. Branch/commit проверяются
отдельным GitHub evidence, не по `/home/Carix`.

Допустимая локальная read-only сверка probe:

```bash
sha256sum cloud/task_116_spec_publish_recovery/remote_gate_a.py
```

Не использовать `checkout`, `pull`, `fetch`, миграции, restart/reload, запись
receipt на Production или publisher для получения Gate A.

## Gate B acceptance

Gate B report может стать `PASS` только если одновременно подтверждены:

- GitHub-verified exact branch/commit и candidate code digest;
- свежесть remote-derived копий и их root/DB fingerprints;
- `UA-0017 + VIN hash + ACTIVE revision digest + rendered facts digest`;
- минимум 10 фактически отображаемых строк дополнительной спецификации;
- основная спецификация заполнила только пустые разрешённые поля;
- четыре legacy-статуса не предлагаются в новой клавиатуре, stale callbacks не
  изменяют данные;
- одна точная ссылка `UA-0017` в каталоге, правильная диагностика, отсутствие
  generic fallback;
- изменения ограничены четырьмя разрешёнными HTML-артефактами target;
- обе root-copy согласованы;
- повторный запуск идемпотентен;
- все failure-injection cases выполнили rollback;
- VIN, цены, медиа, URL, дизайн и остальные карточки не изменены.

## Rollback readiness

Candidate покрывает обычные исключения byte-for-byte снимком HTML и проверкой
scope. Это не покрывает аварийный `SIGKILL` между legacy-write и внутренним
rollback. Поэтому до Production необходим внешний восстановимый snapshot двух
root и затрагиваемых DB, а также проверенная процедура восстановления без
перезаписи новых пользовательских данных.

Триггеры обязательного rollback: publisher exception/false, неверный UID/VIN,
неполная или чужая спецификация, лишняя/отсутствующая ссылка каталога, generic
fallback, изменение вне allowlist, расхождение root, content/digest mismatch.

## Owner gate

Даже verified Gate B сам ничего не публикует. После отдельного Gate B report
владелец должен прислать точную команду:

`ПУБЛИКОВАТЬ UA-0017`

До неё запрещены deploy, migration, service reload, изменение `published` и
любой Production canary.
