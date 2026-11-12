# NEW-CAR-VIN-001 — новое объявление по VIN в CRM-боте

Задача: `tasks/NEW-CAR-VIN-001.md`. Макет: `cloud/crm_new_car_vin_mockup.png`.

Модули (каждый — одна ответственность):
- `ua_new_car_bot.py` — кнопка, ввод VIN, ответ. Карточку создаёт установленный `photo_card`
  (как фото с VIN: марка по VIN, без публикации, повторный VIN не создаёт карточку).
- `edit_cars_ui.py` — точные правки `cars_ui.py`: одна строка над папками экрана «Автомобили» и один блок в конце
  (подключение модуля). Отказ, если правка уже есть или опорная строка не найдена ровно один раз.
- `candidate_builder.py`, `deployment_*`, `make_release.py` — установка по образцу `cloud/kr_prices_bot_001`
  (бэкап, пауза бота, блокировки, проверка, откат).

Тесты: `test_new_car_vin.py` (правка на снимке cars_ui, точные серверные photo_card/ai_filter),
`test_deployment.py` (бэкап/установка/откат на временных файлах).

Порядок: `make_release.py preview` → PR → слияние → `make_release.py launch <PREVIEW_TASK>` (отдельный PR) →
после пробы и «твоя очередь» координатора — `make_release.py install` и запуск (два отдельных PR).
