# Независимый review кода: этап A

**Итог: блокирующих замечаний к текущему ограниченному этапу A после внесённых исправлений не осталось. Production-исполнение не зарегистрировано и по-прежнему запрещено.** Проверены `controller.py`, `git_rehearsal.py` и тонкая обвязка `rehearse_snapshot.py`. Исходники этим review не изменялись.

## Найдено и исправлено авторами

| Замечание | Подтверждённое исправление |
|---|---|
| Inventory связывал байты только с собственными blob SHA; произвольные 40-символьные source commit/tree могли создать ложное утверждение точного snapshot | Закреплена конкретная проверенная историческая пара commit/tree; `verify_tree()` пересчитывает все поддеревья и корень полного inventory; materialized bytes сверяются с Git blob SHA и размером. Удаление записи из inventory или согласованная подмена её байтов больше не сохраняет прежний корневой хеш. |
| Rehearsal проверял только верхние каталоги, поэтому Git `commondir`, alternates и вложенные symlink могли направить plumbing в другой Git-каталог | Закреплены inode owned output/repo/topdirs и config; перед Git проверяется всё дерево на symlink/hardlink/special, запрещены commondir и alternates. Перед каждой mutation дополнительно проверяется абсолютный Git common-dir и повторно проверяются пути. |
| Claims читались по неверному полю `execution_status` | Используется фактическое `task_execution_status`; текущий TASK120 должен оставаться FAILED, а все claims — терминальными. |

## Что подтверждает текущий код

- `execute` безусловно отказывает до preflight/записи. Dry-run не создаёт claim, launch, nonce, HALT или recovery receipt и не делает сетевых запросов. Проверенный control-plane импортируется только из байтов с известным SHA для читающего `verify_execution_mode`.
- Пути входов нормализуются, symlink отвергаются; чтение использует `O_NOFOLLOW`, проверку обычного файла и стабильных inode/размера/mtime. Наборы scoped directories и bytes повторно проверяются после preflight. Выход — новый эксклюзивный JSON только в заданном evidence-каталоге.
- Snapshot привязан к **известному историческому** main `2ce0c3a886f124c5865c564a7073ef1805861f1c`, tree `6f9914b2f742ff4fb4001a5046f86408ad4ecc65`. Это не доказательство, что данный commit является live HEAD во время чтения отчёта. Будущий runner получает живой H отдельно; не должен пытаться закреплять собственный новый commit в своём же исходнике.
- `GitRehearsal.create()` создаёт новый частный fixture; существующий repository не принимается. Фиксированы executable, чистый Git env, пустые hooks/template, запрет протоколов, отсутствие remotes. Все изменения относятся к fixture, не к рабочему checkout.
- Prepared transition связывает первоначальные bytes, local plan, synthetic approval и controller SHA. Проверяется ровно один parent и ровно три пути: удаление HALT, добавление его исходных байтов в archive и локального receipt.
- Git `update-ref <new> <expected-old>` обеспечивает реальный локальный CAS. Drift не переосновывает план. Потеря ответа после CAS распознаётся повторным readback без второго ref update. Подмена PreparedTransition не минует локальную регистрацию подготовленного результата.
- `rehearse_snapshot.py` заново выполняет preflight, помещает проверенные входы в disposable fixture, проверяет переход/replay и неизменность исходных файлов. Его синтетическое approval и отдельный local-model plan явно не объявляются исполнением утверждённого controller plan.

## Границы вывода

Нулевой Actions inventory — состояние предоставленных свежих ответов; `external_writers=UNVERIFIED` и `execution_ready=false` сохранены. Ни dry-run PASS, ни локальный CAS не доказывают удержание live `ua-art-production-writer`, отсутствие внешнего PythonAnywhere writer или отдельное разрешение владельца на снятие HALT.

Защита файлов рассчитана на новый частный fixture `0700` и отказ при обнаруженной подмене. Она не заявляет операционную песочницу против злонамеренного процесса с тем же UID, который меняет файловую систему между проверкой и Git subprocess. Будущий live adapter должен работать только в проверенном runner и не принимать произвольный Git-каталог из CLI.

В существующих результатах авторов: 20 controller tests и 28 Git tests проходят, включая три подмены полного tree, commondir/alternates/objects/refs redirects, конкурентный CAS и потерю ответа. Этот review не запускал повторный широкий suite.

Для следующего ограниченного шага см. `registration-proposal.md`; подготовка этого интеграционного diff уже входит в утверждённое ТЗ.

## Хеши проверенной редакции

- `controller.py`: `d7fed7a80c555fb01fd81fe9bc49f70f79274164c8ecb1f8ec93bfcd13d005e7`
- `git_rehearsal.py`: `ae9dab3a600a33336b2e8abc438e93329db76905b03d1d7780ee7e7fb636bfe9`
- `rehearse_snapshot.py`: `68d3b62077cdacc884b5cd5d3569dc2b520af63cc7b0a5bde5b8c4f848f420fd`
