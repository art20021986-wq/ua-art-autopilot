# UA-ART-RECOVERY-TASK120-002: независимая проверка архитектуры

Результат: **этап A реализуем как инертный контроллер, отдельный PR и dry-run. Поддерживаемый исполняющий маршрут в прочитанных входах пока не доказан; `execution_ready=false`.** Подготовка и слияние файлов только в `cloud/recovery_task120_002/` не должны менять HALT, режим, очередь или создавать launch marker.

Проверены предоставленное ТЗ и текущие локальные копии `automation/control_plane.py`, `production_queue.py`, `autostart_intake.py`, `transaction_watchdog.py`. Это исследование исходников, без запуска их команд, сети и изменения управляющего состояния. После получения YAML дополнительно прочитаны workflow CRITICAL, watchdog, autostart и orchestrator. Подтверждены группы: CRITICAL production и watchdog — `ua-art-production-writer`, оба с `cancel-in-progress: false`; intake использует отдельные группы, поэтому общей блокировки production недостаточно для сериализации всех Git writers.

## Что уже обеспечивает текущий механизм

- `verify_execution_mode()` проверяет не только наличие HALT: он связывает mode, epoch, автоматическое согласование владельца, TASK107 receipt, runtime manifest и все 18 закреплённых путей. Историческое согласование и `EXECUTION_MODE` оба содержат хеш manifest; `generated_at` manifest не может быть позже `activated_at` режима.
- `verify_production_credential_workflow_policy()` требует **точное** множество девяти активных YAML и их событий. Для CRITICAL/watchdog также проверяются точные SHA workflow, набор privileged jobs, изолированный Python, привязка runtime и граница токена. Новый YAML или дополнительный privileged job не является уже разрешённым расширением.
- `claim_request()` проверяет активные durable claims и конфликты ресурсов; `GLOBAL_PRODUCTION` конфликтует со всеми ненулевыми записывающими scope. Но это не распределённая блокировка само по себе: функция читает и пишет локальный checkout, а согласованность между runners обеспечивается внешней сериализацией и Git-публикацией.
- `transaction_watchdog.assert_clear()` отказывает при `PREPARING`, `OPEN`, `ROLLING_BACK` и неизвестных статусах. Терминальность шести транзакций не доказывает отсутствие активного Actions writer или ожидающего запуска.
- `production_queue.find_blockers()` — проверка приоритета очереди. Она игнорирует тот же workflow path, более новые билеты и задачи, не распознанные по маркерам названия. **`PRODUCTION_QUEUE_PASS` не означает, что все production writers и все ожидающие запуски отсутствуют.**
- `autostart_intake.validate_launch()` первым шагом проверяет режим и HALT, затем exact request, epoch, expiry, owner authorization, production gates и replay ledger/nonce. Обычный autostart не является разрешённым транспортом для обхода HALT. Триггер autostart ограничен изменениями `tasks/launch/AUTO-*.json`; recovery-коммит не должен затрагивать эти пути.

## Минимальный контроллер этапа A

В `cloud/recovery_task120_002/` достаточно чистого валидатора входов, детерминированного построителя плана, модели Git-перехода, CLI с dry-run по умолчанию и изолированных тестов. Тесты Git/CAS выполняются только во временном репозитории. Читаемые входы фиксируются SHA-256 и точным main OID; неизвестный файл, неполный inventory, неизвестный статус, незавершённая транзакция, активный claim/writer или непроверенный запуск дают конкретный `NOT_READY`.

Разделить два результата:

- `plan_valid`: структура и конкретные привязки TASK120 корректны; допустимый переход перечислен полностью.
- `execution_ready`: все свежие входы проверены, отдельная команда владельца на exact plan предъявлена и существует проверенный runner, действительно удерживающий общую writer-блокировку.

Без зарегистрированного runner даже корректный dry-run возвращает `execution_ready=false` и `RUNNER_NOT_REGISTERED`. Нельзя заменять доказательство блокировки флагом `--writer-lock-held`, заявлением вызывающего процесса или наличием токена. Исполняющая граница до интеграции отказывает; она не делает прямой GitHub mutation из произвольной машины.

Допустимо повторно использовать читающую проверку режима с явным recovery-контекстом только для этой конкретной остановки. Это не разрешение запускать новый production request с `allow_halt_for_recovery` и не изменение общего gate.

## Атомарный переход Git

План задаёт ровно три изменения относительно утверждённого parent main `H`:

| Путь | Действие |
|---|---|
| Новый `state/halt_history/UA-ART-RECOVERY-TASK120-002/halt.json` | Добавить **исходные байты** текущего HALT, без повторной сериализации |
| Новый `state/halt_history/UA-ART-RECOVERY-TASK120-002/receipt.json` | Добавить неизменяемое свидетельство конкретного управляющего перехода |
| `state/AUTOPILOT_HALT.json` | Удалить только blob с утверждёнными OID/SHA-256 |

Указанные пути уже закреплены в конкретном `mutation_plan` контроллера и проверяются как точное множество изменений. Оба новых пути обязаны отсутствовать в `H`. Все прежние request/claim/transaction/reconciliation/launch/nonce/consumed records и `EXECUTION_MODE` сохраняются байт в байт.

Исполняющий runner использует существующий подход с отдельным `GIT_INDEX_FILE` в runner temp: `read-tree H`, только перечисленные additions/deletion, `write-tree`, `commit-tree -p H`. До отправки сравниваются полное множество изменённых путей, исходный HALT blob и новые payload-хеши. **Один Git commit и один атомарный ref CAS** публикуют архив, receipt и снятие HALT вместе. Последовательные Contents API PUT/DELETE не подходят.

CAS должен требовать remote `refs/heads/main == H`, а новый commit — иметь ровно одного parent `H`. Если используется Git push, нужен явный expected-old ref lease/эквивалентная операция CAS, без обхода branch protection и без возможности опубликовать не-fast-forward commit. Нельзя делать rebase, автоматически подставлять новый parent или повторять переход на свежем main: дрейф требует нового dry-run и утверждения.

Receipt связывает transition ID, старый HALT SHA, task/run/request/epoch/reconciliation, `parent_main_sha`, code/manifest/plan/approval hashes и конкретный исход `CONTROL_HALT_CLEARED`. Он не должен называться production receipt или переписывать TASK120 как успешный rollback. **Собственный commit SHA нельзя включать в receipt внутри того же commit:** это циклический хеш. Фактический новый commit OID сообщается отдельным результатом readback, а receipt содержит parent и независимые привязки.

## Сериализация и свежесть

Перед переходом runner должен быть привязан к проверенному workflow/source OID и удерживать **ту же реальную глобальную concurrency group**, что действующие production writers, с `cancel-in-progress: false`. Фактическое имя — `ua-art-production-writer`: оно задано на уровне workflow CRITICAL при `production_required=true` и у watchdog. Autostart использует `uaart-global-autostart-intake-${{ github.sha }}`, orchestrator — `uaart-intake-main`; их Git-записи не сериализуются этой production-группой. Поэтому expected-main CAS и полный active-run inventory остаются обязательными. Локальный `flock` на машине пользователя или отдельная новая concurrency group не заменяют эту сериализацию.

Уже внутри блокировки необходимо получить текущий main и полный свежий Actions inventory, проверить все активные/ожидающие статусы с полной пагинацией, исключая только точный run самого recovery. Неизвестные workflow/run-классы дают отказ, а не считаются непроизводственными по названию. Затем повторно проверяются durable claims, транзакции, launch markers, nonce reservations и consumed ledgers. Любая непроверенная ожидающая задача блокирует переход; очередь не очищается и запуски не отменяются автоматически.

Snapshot очереди должен связывать repository, текущий recovery run, время получения, полноту пагинации и нормализованный список run ID/status/workflow/source. План закрепляет **семантический хеш** очереди и явное максимальное допустимое время её давности; новый `captured_at` при свежем чтении не должен создавать бессмысленную смену плана, если сама очередь не изменилась. Не подменять свежий снимок давним JSON. Повторный preflight и CAS выполняются до освобождения блокировки.

## Отдельное утверждение и поведение при сбое

Утверждение этапа A не включает переход. Исполнение требует отдельной команды владельца на task/transition ID, exact plan SHA, controller SHA, main `H`, HALT SHA и epoch, с проверяемым происхождением через утверждённый runner. Самоподписанный JSON с `owner_authorized=true` без установленного маршрута авторизации не достаточен.

После слияния подготовительного PR main изменится: нужен новый dry-run на фактическом main. Нельзя сначала закрепить план на `H`, затем отдельным commit на main записать его approval и сохранить ожидание `H` — это создаёт самопорождающийся дрейф. Практичный вариант: detached подтверждение из доверенного существующего маршрута, хеш/доказательство которого включается в единственный transition receipt. Новый транспорт или схема доверия требуют отдельного явного review.

До ref CAS исходный HALT остаётся на main, поэтому сбой подготовки не требует восстанавливать стоп. При неясном ответе push выполняется readback: наличие точного receipt, исходного архива, отсутствие HALT и идентичность transition определяют уже завершённую операцию. Повтор того же ID — read-only результат, без второго commit. Неясный результат не повторяется наугад. Если postcheck после подтверждённого CAS требует вернуть управляющий стоп, это отдельный предусмотренный планом CAS при удерживаемой блокировке; старые receipt/архив не удаляются, новая ошибка документируется.

## Реальный предел интеграции

В текущем allowlist нет команды/runner снятия HALT. Использовать watchdog под чужим предметом, добавить произвольный workflow, переписать pinned hashes без их review или выдать task-коду GitHub write token нельзя. Поэтому **полностью завершить этап A можно сейчас**, оставив исполняющую границу закрытой.

Активация будущего runner требует отдельного проверяемого diff существующей управляющей системы: workflow policy, точные workflow SHA, runtime closure/manifest и связанные mode/owner approval привязки. Текущий временной порядок `generated_at <= activated_at` также должен сохраняться корректным; просто пересчитать manifest недостаточно. Новые права и production secrets для Git-only recovery не нужны и не добавляются. До рассмотрения такой интеграции отчёт должен честно указывать `RUNNER_NOT_REGISTERED`, а не обещать исполнимый переход после одной команды.

## Короткая запись решения

Принято для этапа A: инертный `cloud/` controller формирует exact plan и трёхфайловый Git tree proposal; rehearsal исполняет архив/receipt/HALT deletion и `update-ref <new> <expected-old>` исключительно в **самостоятельно созданном новом временном Git fixture**, без remotes и пользовательского параметра произвольного рабочего репозитория. Approval — detached input с task/transition ID, plan SHA, code SHA и base commit; оно не меняет main. Нельзя считать простое поле approval доказательством полномочий production-runner.

Production CLI apply остаётся отключённым с `NOT_READY_RUNNER_NOT_REGISTERED`. Это честное завершение подготовительного этапа, если отчёт отдельно сообщает: код/план/rehearsal проверены; реального снятия HALT и зарегистрированного маршрута пока нет. Подготовка следующего ограниченного интеграционного diff входит в уже утверждённое ТЗ и **не требует повторного согласования подготовки**. Отдельная команда понадобится для фактического управляющего перехода, как уже установлено владельцем.

Основные ограничения существующих защищённых файлов, которые нельзя молча обходить или править в cloud-only PR:

1. `production_queue.py` проверяет очередность, а не полную тишину; название задачи и same-path исключение не подходят для восстановления HALT.
2. CRITICAL/watchdog разделяют production lock, intake/orchestrator имеют другие группы. Одного lock недостаточно против движения main; необходим exact ref CAS без автоматического выбора нового parent.
3. `control_plane.py` связывает 18 runtime paths с manifest, mode и историческим owner approval; для workflow ещё действуют точные SHA и точный набор jobs/events. Пересчёт одного manifest не является корректной активацией runner.
4. `transaction_watchdog.assert_clear()` означает отсутствие pending transaction, а не отсутствие active claim, run, непросмотренного launch или writer.
5. `atomic_json()` обеспечивает лишь запись отдельного локального файла. Тройной переход HALT/archive/receipt должен стать видимым только одним Git tree/ref update.
6. `claim_request()` сначала отвергает HALT: запуск recovery как обычной production/nonproduction задачи через прежний intake не является зарегистрированным маршрутом.

Минимальная приёмка rehearsal: baseline HALT неизменён до CAS; ровно три разрешённых пути после CAS; архив байт в байт; отказ на drift/чужой HALT/неверное approval; отказ CAS при конкурентном main; idempotent readback без второго commit; no-op/fail-closed production CLI.
