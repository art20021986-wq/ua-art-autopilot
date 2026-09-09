# Следующий ограниченный шаг: регистрация runner TASK120

Это конкретное предложение интеграционного diff **в рамках уже утверждённого UA-ART-RECOVERY-TASK120-002 v1.0**. Подготовка не требует нового ТЗ или повторного разрешения на подготовку. Настоящий документ ничего не активирует; фактическое снятие HALT остаётся предметом ранее установленной отдельной команды владельца на проверенный результат.

## Выбранный маршрут

Расширить существующий `uaart_transaction_watchdog.yml` отдельной явно названной веткой `recover_task120_halt`, не переименовывая её под rollback/preparing. Это предпочтительный существующий workflow: у него уже есть Git state writer, `actions: read` в `finalize_rollback` и общая группа `ua-art-production-writer` с `cancel-in-progress: false`. Использовать backup/monitor/maintenance хуже: они read-only и потребовали бы расширения их прав. Новый активный workflow не добавлять.

До review подготовить **неактивную** версию YAML по пути:

`cloud/recovery_task120_002/integration/uaart_transaction_watchdog.proposed.yml`

Этот файл находится вне `.github/workflows` и не регистрируется Actions. Рядом разместить точный patch и результаты policy-тестов; не класть незарегистрированный YAML в активную директорию даже с предполагаемым отключённым trigger.

## Конкретные файлы будущего проверяемого diff

| Файл | Изменение |
|---|---|
| `.github/workflows/uaart_transaction_watchdog.yml` | Явный `workflow_dispatch` для этой операции; отдельные validate и Git-persist jobs; те же main-only, global group, isolated Python, trusted runtime closure, data-only artifact и token boundaries. Существующая scheduled rollback-ветка сохраняется. Новая ветка не получает PythonAnywhere secret и не вызывает backup/install/CRM/site/dispatch/rerun. |
| `automation/task120_halt_recovery.py` | Тонкий trusted adapter для exact plan/owner-command, fresh main/tree/Actions, writer context, трёхфайлового Git proposal, CAS и readback. Он не принимает произвольный repository/controller/command из входов. Код текущего cloud planner переносится или подключается только через явную полную hash closure; локальная Git fixture не становится production backend. |
| `automation/control_plane.py` | Добавить точный новый runtime path, допустимый dispatch event и именованные recovery jobs; закрепить SHA окончательного watchdog. Добавить узкую проверку additive runtime activation binding, описанную ниже. Прежние gate/approval/backup/health/replay требования обычных production задач не менять. |
| `state/AUTOPILOT_RUNTIME_MANIFEST.json` | Новая проверенная closure вместе с изменённым кодом. Это не отдельное ручное «исправление хешей», а часть того же обозримого bundle. |
| `state/EXECUTION_MODE.json` | Только ссылка/хеш новой runtime closure, если она активируется; семантический mode, epoch, все production-required flags и replay prohibition сохраняются. Историческое owner approval не редактировать. |
| Новые `state/runtime_activations/UA-ART-RECOVERY-TASK120-002.json` и `state/runtime_manifests/<old-manifest-sha>.json` | Неизменяемое activation-свидетельство и исходные байты прежнего manifest. Связать старые approval/mode/manifest/source с новой closure и проверенным интеграционным diff. Создание этих записей само по себе не доказывает разрешение; validator проверяет фактическое основание установленной авторизации. |
| Тесты control-plane и `cloud/recovery_task120_002/tests/` | Точный allowlist, отказ при чужом task/HALT/approval/runtime, отсутствие secrets у recovery branch, Git CAS/drift/replay и сохранение всех прежних production gates. |

## Почему требуется отдельная additive authority binding

Сейчас `EXECUTION_MODE` и `TASK107-R2-AUTOMATIC-MODE.json` оба закрепляют один manifest SHA, а `generated_at` manifest ограничен исходным `activated_at` режима. Поэтому замена только YAML или manifest гарантированно ломает штатную проверку. Переписывать старое согласование владельца новым runtime SHA нельзя: это изменило бы смысл исторического решения.

Предлагаемый narrow extension сохраняет исходное approval байт в байт и проверяет цепочку:

**историческое approval и старый manifest → конкретное reviewed runtime-activation receipt → новая точная closure.**

Receipt должен закреплять исходный main, старый approval SHA, старый mode/manifest SHA, новый manifest SHA, task ID, activation revision/time, источник авторизации и хеш полностью проверенного интеграционного diff. Он допускает только это расширение runtime, не создание новой глобальной production-авторизации. Проверка времён использует отдельное время runtime activation; нельзя задним числом менять исходное approval/activated_at или удалять проверку времени. Несовпадение любого звена, отсутствие receipt либо неподтверждённая авторизация дают отказ.

Эта цепочка **ещё не реализована текущим Stage A**. Её точная схема и trust boundary входят в следующий review. Простой JSON с `approved=true` или факт наличия файла не заменяют согласование; текущий cloud-only код такую запись не создаёт и не применяет.

## Последовательность работ

1. Подготовить неактивный YAML, adapter, полный patch проверок и модели activation receipt; выполнить локальные policy/CAS тесты. Все действующие state-файлы и HALT остаются неизменными.
2. Представить один согласованный интеграционный bundle: точные исходные/конечные hashes, новый manifest, связь со старым approval без его перезаписи и явное отсутствие новых credential scopes/secrets. Проверить, что добавленный runtime path входит во все bootstrap closures и не пропускается до первого repository Python или выдачи token.
3. Регистрацию/активацию применять только как отдельно обозримый control-plane diff по действующему порядку полномочий. Это не обычный merge текущего инертного PR «с побочным эффектом». HALT во время такой регистрации сохраняется; scheduled jobs не должны автоматически выполнять recovery или запускать старую очередь.
4. После регистрации получить живой main `H`, tree и полную свежую очередь; построить новый plan из доверенно полученного состояния. Отказаться от константы исторического main в live adapter. Получить предусмотренную ТЗ отдельную команду на **этот** результат перед снятием HALT.
5. В зарегистрированном runner удерживать `ua-art-production-writer`, проверить источник/closure/approval/queue и выполнить один commit+CAS только для:
   - удаления `state/AUTOPILOT_HALT.json`;
   - добавления `state/halt_history/UA-ART-RECOVERY-TASK120-002/halt.json`;
   - добавления `state/halt_history/UA-ART-RECOVERY-TASK120-002/receipt.json`.
6. Проверить readback и неизменность остальных ограничений; только затем освободить writer group. Итог — управляющий стоп завершён, не публикация карточек и не Gate B спецификации.

## Критерий отсутствия обхода

Никаких новых секретов, расширения credential scopes, arbitrary task execution в privileged job, `allow_halt_for_recovery` для другой production задачи, очистки очереди или сброса nonce/consumed. Existing intake writers имеют отдельные concurrency groups, поэтому даже при удержании production group обязателен expected-main CAS. При движении main runner не rebase-ит и не подставляет новый parent без нового точного плана.

До завершения регистрации текущий итог остаётся: **подготовительный код/PR/dry-run/rehearsal готовы; `execution_ready=false`, `NOT_READY_RUNNER_NOT_REGISTERED`.** Это ограничение исполняющего маршрута, а не просьба заново согласовать уже утверждённую подготовку.
