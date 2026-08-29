# TASK 082 — CRM-VIN4-TITLE-001 v1.0

## Прямая команда владельца

29.08.2026 владелец потребовал немедленно, максимум за 30 минут, изменить действующий Telegram CRM-бот UA ART: по каждому автомобилю и в каждой карточке дополнить название последними четырьмя символами VIN, визуально выделив их жирным основным цветом текста. Изменение требуется для всех текущих UA-0001…UA-0013 и автоматически для всех будущих карточек. Эта команда разрешает безопасную установку в production только после backup, deterministic tests, live shadow/canary и автоматического отката при любом FAIL.

## Важная техническая трактовка Telegram

Telegram не разрешает задавать произвольный цвет отдельному фрагменту текста. В обычном сообщении использовать HTML `<b>…</b>` и стандартный основной цвет клиента (на светлой теме он чёрный). В тексте InlineKeyboardButton частичное форматирование/цвет невозможны: там добавить суффикс VIN4 обычным текстом. Не вставлять HTML в подпись кнопки.

## Единый формат

Текстовая строка/заголовок:
`UA-0013 · Mercedes-Benz Б-КЛАССА 2015 · VIN <b>1234</b>`

Кнопка выбора, если она содержит название:
`UA-0013 · Mercedes-Benz Б-КЛАССА 2015 · VIN 1234`

VIN4 — последние 4 символа нормализованного полного VIN (`strip`, убрать пробелы/дефисы, uppercase). VIN может заканчиваться буквами, поэтому брать символы, а не только цифры. Нельзя раскрывать полный VIN в списке.

## Обязательная область

1. Экран `Все автомобили` из приложенного скриншота: все строки UA-0001…UA-0013.
2. Все inline-кнопки выбора автомобиля, где сейчас видны UA-ID/марка/модель/год.
3. Заголовок открытой CRM-карточки и повторные заголовки после редактирования/медиа/этапов, если они формируются отдельно.
4. Все будущие карточки через один централизованный renderer/helper; никакого hardcode для 13 машин.
5. Данные брать только из существующего `cars.vin`; schema и CRM rows не менять.

## Fail-safe для VIN

- Валидный нормализованный VIN: ровно 17 символов `[A-HJ-NPR-Z0-9]`, показывать последние 4.
- Если VIN отсутствует/невалиден, карточка должна оставаться доступной для редактирования, но вместо выдуманных символов показать жирное `VIN НЕТ` в текстовом заголовке и `VIN НЕТ` в кнопке. Публикационный валидатор не ослаблять.
- Любые значения обязательно HTML-escape до `parse_mode="HTML"`; запрет двойного суффикса `VIN` при повторном рендере.
- Не менять названия/статусы/этапы/цену/фото/видео/описание/контейнер/ETA/published.

## Реальный доступ и маршрут

- Production: `/home/Carix`; bot source includes active `cars_ui.py`; DB `/home/Carix/crm.db`; launcher exactly `python3.10 /home/Carix/start_safe.py`.
- Использовать уже работающий GitHub secret `PYTHONANYWHERE_API_TOKEN` и PythonAnywhere API pattern из TASK 067/068/077. Он подтверждён рабочими Gate A/production runs. Не просить пароль, логин или новый токен.
- Не использовать runtime LLM; tokens = 0.

## Исполнение

Сделать полный runnable package `cloud/task_082_vin4_title/`:
- GET live source + read-only DB shadow;
- sanitized evidence (для 13 cards только UA-ID, VIN4/missing marker, без полных VIN);
- AST/full-SHA anchored patcher активных render functions;
- backup + atomic installer + exact launcher restart;
- immediate and delayed postcheck;
- offline tests and live-copy canary;
- controller with rollback;
- production workflow under package for Codex to copy into `.github/workflows/task082_vin4_title_deploy.yml`.

Workflow должен запускаться push после копирования, использовать только `PYTHONANYWHERE_API_TOKEN`, выполнить `BACKUP → live shadow → local canary → atomic source-only install → restart → immediate + delayed postcheck`. Любой drift/failure = rollback source + restart + FAIL. DB/site/media writes запрещены.

## Acceptance

- 13/13 текущих строк имеют ровно один VIN4/или доказанный VIN НЕТ; все валидные значения точно совпадают с последними четырьмя символами DB VIN.
- Future fixture UA-9999 проходит тот же helper.
- Text HTML has exactly one bold VIN4; button label has no markup and exactly one VIN4.
- HTML escaping/injection, lowercase/spaces, suffix letters, invalid/missing, idempotency, Telegram limits covered.
- Bot getMe/launcher health PASS before and after; existing buttons/callback_data unchanged.
- `crm.db` SHA/quick_check, published rows, media hashes and protected website/card hashes unchanged.
- exact changed production file set should normally be only `cars_ui.py`; if active renderer is demonstrably in another bot source, fail closed unless evidence proves the minimal exact set.
- delayed check confirms no later generator overwrote the patch.
- report exact backup path, changed file SHA before/after, 13 sanitized title examples, and `PRODUCTION_TOUCHED: YES` only after verified PASS.

Обновить `cloud/latest_status.md` и `cloud/owner_reply.md`. Не останавливаться на просьбе о доступе: применить существующий рабочий transport из TASK 067/068/077.
