# TASK 082 — Bounded production install procedure

Этот документ описывает единственную разрешённую процедуру установки пакета
`catalog_guard.py` + `publikaciya_wrapper.py` в production. Выполняется
контроллером/исполнителем на стороне PythonAnywhere, НЕ Claude/Cloud.

## Разрешённый scope файлов

- `/home/Carix/video/katalog.html`
- `/home/Carix/site/katalog.html`
- новый модуль guard (например `/home/Carix/common/catalog_guard.py`)
- bounded wrapper вокруг активного `publikaciya.opublikovat`
- restart `/home/Carix/start_safe.py`

Запрещено: CRM rows, VIN, цена, описание, фото/видео, индивидуальные страницы,
любые прочие файлы.

## Шаги

1. **Fresh live audit.** Прочитать текущие CRM записи (status, ua_code, vin,
   title_base, description_snippet) и текущее состояние опубликованных
   индивидуальных страниц/media (main_photo_absolute_url, individual_page_url)
   непосредственно перед записью. Не использовать кэш.
2. **Backup.** Скопировать оба текущих файла `katalog.html` в persistent backup
   директорию с таймстампом, вычислить и сохранить SHA-256 обоих файлов.
3. **Сборка в памяти.** Вызвать `catalog_guard.rebuild_all(cars, pages)` затем
   `catalog_guard.assemble_catalog_html(cards)`. Результат — HTML-строка,
   которая пока не записана ни в один production файл.
4. **Проверка перед записью** (все пункты обязательны, любой FAIL останавливает
   установку без изменения production):
   - UA-0011: stage == 2, category == 'more', заголовок содержит `VIN 4289`,
     main_photo_url — абсолютный URL, ровно одна карточка UA-0011 в собранном
     HTML;
   - UA-0009: ровно одна карточка присутствует, stage/media не изменились
     относительно текущего live-состояния CRM/media;
   - Все прочие существующие карточки отрендерены единым шаблоном (`class="catalog-card"`
     с блоком `catalog-card__media`), отсутствуют текстовые fallback-карточки;
   - Число карточек в новом HTML соответствует числу UA-кодов с успешным рендером
     (`rebuild_result['cards']`), исключённые записаны в `rebuild_result['excluded']`
     с причиной для аудита;
   - DB normalized published rows идентичны до/после (guard не производил запись в CRM);
   - Individual UA pages и media UA-0011 байт-идентичны до/после (guard их не читал
     на запись, только на чтение).
5. **Атомарная запись обоих файлов как одна транзакция.**
   - Записать новый HTML во временные файлы рядом с целевыми путями;
   - Проверить, что оба временных файла синтаксически валидны и проходят пункт 4
     повторно на диске;
   - `os.replace()` (atomic rename) для `video/katalog.html`, затем для
     `site/katalog.html`;
   - Если второй `os.replace()` не удаётся — немедленно восстановить первый файл
     из backup (оба должны быть согласованы или оба откатены).
6. **Restart** только `/home/Carix/start_safe.py`.
7. **Immediate HTTP verification** обоих каталогов: 200 OK, наличие карточки
   UA-0011 с фото и `VIN 4289`, фильтр `?stage=more` / `?f=ferry` / `?etap=2`
   возвращают ту же карточку.
8. **Delayed HTTP verification** — повторная проверка через контролируемый
   интервал (согласно рантайму контроллера) для исключения кэш-эффектов.
9. **Rollback политика.** Любой FAIL на шагах 4, 5, 7 или 8 → восстановить оба
   файла из backup SHA-256-verified preimage, перезапустить восстановленный
   `start_safe.py`, зафиксировать инцидент.

## Явное примечание об ответственности

Claude/Cloud подготовил детерминированный, протестируемый пакет (`catalog_guard.py`,
`publikaciya_wrapper.py`) и данную процедуру. Claude/Cloud НЕ выполнял шаги 1–9 на
реальном production — эти шаги должен выполнить контроллер/исполнитель с прямым
доступом к PythonAnywhere, используя письменное разрешение владельца, зафиксированное
в TASK 082, как действующий Gate B mandate для этого исполнения.
