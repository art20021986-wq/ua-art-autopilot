# PAGES-LAG-FIX-001 — самопроверка CRM только в боте, причина ошибки и повтор сборки

Разбор: `cloud/pages_lag_probe_001` (пробы 20261125, -R2, -R3), `cloud/latest_status.md` (PAGES-LAG-001).
25.11 08:53 UTC владельцу пришло «CRM: страницы сайта отстали от базы, и пересобрать их не получилось»: одна сборка
stranica.py дала код 1, следующая через 5 мин прошла. Причину журнал не хранил. Самопроверку (samokontrol) запускал
`~/.local/lib/python3.10/site-packages/usercustomize.py` в КАЖДОМ процессе Python аккаунта, и каждый мог сам запустить сборку.

- `edit_usercustomize.py` — блок «UA-V74 samokontrol» импортирует samokontrol только когда в sys.argv есть start_safe или
  run_all (бот: always-on «python3.10 /home/Carix/start_safe.py»). Остальные блоки файла не тронуты. Для Python 3.13
  блока samokontrol нет — файл не меняется.
- `edit_samokontrol.py` — `sobrat()`: при коде ≠0 пишет в samokontrol_log.txt хвост ошибки (600 символов) и через 60 с
  повторяет сборку; сообщение владельцу — только если обе попытки не прошли.
- Превью (python3.10 на сервере, временная папка): блок-кандидат как usercustomize коротких программ — «сторож» только у
  start_safe.py и run_all.py, не у stranica.py, задач автопилота и `-c`.
- Установщик — образец `cloud/photo_add_001` (бэкап, пауза бота, замки, откат). Бот перезапускается и берёт новую версию.
- Тесты: `test_pages_lag_fix.py` (правки на точных копиях живых файлов, проверка превью, повтор), `test_deployment.py`.
