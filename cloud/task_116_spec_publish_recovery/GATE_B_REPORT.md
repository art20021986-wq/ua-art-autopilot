# TASK116 — Gate B report

**Contract:** `UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001` v1.0  
**Report date:** 2026-09-07  
**Gate B verdict:** `NOT_RUN / NOT_ELIGIBLE`  
**Production gate:** `CLOSED`  
**UA-0017 release:** `BLOCKED`; **Production state:** `UNKNOWN_REMOTE_NOT_OBSERVED`

## Executive result

Gate B не выполнялся на свежей копии фактического удалённого состояния.
Production URL, DB, runtime, service и publisher этим шагом не вызывались и не
изменялись. Публиковать `UA-0017` на основании локальных проверок запрещено.

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
| Remote Gate A | NOT_RUN | Нет |
| Gate B на remote-derived копиях | NOT_RUN | Нет |
| Owner Production command | NOT_GIVEN_FOR_RELEASE | Нет |

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

1. Выполнить `remote_gate_a.py` на согласованном remote-root и сохранить его
   stdout внешним неизменяемым контуром доказательств.
2. Установить фактические DB и два web-root. При наличии SQLite `-wal` immutable
   probe может не видеть незачекпойнченные записи; нужна согласованная read-only
   snapshot/copy, подготовленная платформой вне probe.
3. Предъявить отдельную branch и exact commit через GitHub branch/commit/PR evidence.
4. Связать candidate digest с этим commit; не использовать строку из кода как
   замену Git evidence.
5. Создать свежие восстановимые копии remote-state и применить patcher только к
   ним.
6. Проверить `UA-0017` и минимум по одной старой и новой карточке, не изменяя
   Production.
7. Установить внешний доверенный release-controller: durable одноразовый owner
   nonce, OS-level write allowlist, crash-durable snapshot/restore и проверка
   computed CSS в браузере. In-process callbacks и RAM-снимок этого не заменяют.

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
