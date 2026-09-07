# TASK116 execution candidate

Этот каталог содержит fail-closed candidate для контракта
`UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001` и документацию проверки. Он не является
Production release.

## Текущий статус

- Режим candidate: `PREVIEW_ONLY`.
- Remote Gate A: не выполнен.
- Gate B: не выполнен.
- `UA-0017`: заблокирована до verified Gate B и отдельной команды владельца.
- Production-действия этого документационного шага: `0`.
- Candidate фиксируется только в отдельной ветке
  `codex/ua-art-crm-spec-publish-recovery-001`; точный head подтверждается
  GitHub branch/commit evidence. `/home/Carix` может не быть Git checkout и не
  используется для этой проверки.

## Состав candidate

| Файл | Назначение | Запись при простом импорте |
|---|---|---|
| `recovery_core.py` | Чистые политики UID/VIN, ревизий, preflight, scope и статусов | Нет |
| `spec_revision_store.py` | Предлагаемое неизменяемое versioned-хранилище спецификаций | Только при явном вызове write API |
| `vin_primary_decoder.py` | Строгий VIN decoder adapter | Сеть только при явном вызове |
| `vin_base_spec_service.py` | Empty-only CAS writer основной спецификации | Только при явном вызове write API |
| `vin_ingestion.py` | Координация exact-card подготовки | Через переданный backend |
| `ua116_runtime_bridge.py` | Предлагаемый runtime bridge | Только при явном вызове runtime API |
| `preview_release.py` | Версионная сборка только под разрешённым Preview root | Только в явно указанном Preview |
| `integration_patcher.py` | Fresh-source patcher | Только в явно указанной изолированной копии |
| `atomic_publish.py` | Guarded Production adapter с owner/Gate B gate и rollback | Только после явного вызова и всех gates |
| `sandbox_gate_b.py` | Локальная candidate-матрица во временном каталоге | Не является Remote Gate B |
| `remote_gate_a.py` | Read-only инвентаризация удалённого состояния, один JSON в stdout | Нет |

Простой импорт модулей не является установкой. `integration_patcher.py` и
`atomic_publish.py` нельзя запускать против `/home/Carix` или другого live-root
до выполнения Gate B и команды владельца.

## Этапы A–F

- **A:** read-only BEFORE-инвентаризация; отдельная ветка доказывается в GitHub,
  фактических root/DB/runtime и состояния `UA-0017`.
- **B:** неизменяемая дополнительная спецификация и сохранность основания сайта.
- **C:** empty-only основная спецификация после VIN с provenance и CAS.
- **D:** скрытие четырёх legacy-кнопок без удаления исторических данных; stale
  callback блокируются без изменения карточки.
- **E:** exact-card preflight, атомарная сборка, валидация и rollback публикации.
- **F:** удалённый Gate B на копиях, отдельный owner gate и единичный canary.

Полные требования находятся в `tasks/task_116.md`.

## Честная иерархия доказательств

1. Unit/local candidate run подтверждает только поведение локального кода.
2. Preview run подтверждает только изолированную копию.
3. `remote_gate_a.py` наблюдает фактическое удалённое состояние, но ничего не
   устанавливает и не является Gate B.
4. Gate B должен применить точный candidate к свежим копиям наблюдённого
   удалённого состояния и выдать свежий target-bound receipt.
5. Только после verified Gate B владелец отдельно разрешает Production.

`evidence/gate_b_local.json` содержит свежий source-bound результат 14/14
локальных candidate-проверок, manifest кода и явные блокеры. Поля
`gate_b_eligible=false`, `production_eligible=false` и
`release_authorization=BLOCKED` запрещают использовать его как Gate B receipt.

## Безопасные локальные проверки

Запуск тестов без записи evidence:

```bash
cd cloud/task_116_spec_publish_recovery
PYTHONDONTWRITEBYTECODE=1 python3 sandbox_gate_b.py
```

Проверка probe через `py_compile` должна направлять bytecode вне репозитория:

```bash
python3 -c 'import py_compile; py_compile.compile("remote_gate_a.py", cfile="/tmp/task116-remote-gate-a.pyc", doraise=True)'
```

Локальный `PASS` в этих командах нельзя переименовывать в Gate B.

## Remote Gate A: только чтение

VIN `UA-0017` в текущем пакете неизвестен. Перед запуском получить его из
единственной точной CRM-строки `UA-0017` read-only и подставить без догадок:

```bash
python3 -B remote_gate_a.py \
  --root /home/Carix \
  --uid UA-0017 \
  --vin <EXACT_UA0017_CRM_VIN>
```

Probe:

- не импортирует приложение;
- не выполняет HTTP-запросы;
- не создаёт temp, cache, log или evidence-файлы;
- открывает SQLite только как `mode=ro&immutable=1` и исполняет только SELECT;
- выполняет Git `rev-parse` с `GIT_OPTIONAL_LOCKS=0`, только если `.git`
  действительно присутствует, но маркирует это только как наблюдение;
- печатает ровно один JSON-объект в stdout, включая ошибки;
- всегда сообщает `gate_b.status=NOT_RUN`.

Probe никогда не выдаёт `PASS`: только `FAIL` либо `UNKNOWN` и код возврата 1,
пока результат требует проверки. JSON сохраняется внешним контуром
доказательств, не самим probe. Отдельная ветка и commit подтверждаются
независимо через GitHub evidence, а не через Production-root.

## Обязательная Gate B-матрица

На свежих изолированных копиях фактического remote-state проверить:

1. B: старая ACTIVE-спецификация переживает пустой refresh и несвязанные
   изменения; UID/VIN/content digest совпадают.
2. C: основная спецификация заполняет только пустые поля; ручные данные,
   пробег и цвет не подменяются VIN-догадками.
3. D: четыре legacy-кнопки скрыты, stale callbacks ACK/blocked, history не
   удалена.
4. E: exact UID/VIN из CRM, worker health, обе web-root, ровно одна
   ссылка каталога, generic fallback и scope guard.
5. Failure injection: outage decoder, неполная спецификация, publisher
   exception, расхождение root, изменение вне allowlist, повторный webhook.
6. Rollback: байтовое восстановление разрешённых HTML при каждом обычном сбое;
   внешний snapshot отдельно покрывает аварийное завершение процесса.

## Production gate

До verified Gate B запрещены deploy, patch, migration, restart, reload,
переключение `published` и публикация `UA-0017`. После Gate B candidate принимает
только точную отдельную команду владельца:

`ПУБЛИКОВАТЬ UA-0017`

Команда разрешает только один target-bound canary. Она не разрешает массовую
публикацию других карточек.
