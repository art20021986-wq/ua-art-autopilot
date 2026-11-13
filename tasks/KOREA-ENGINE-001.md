# KOREA-ENGINE-001 — тип двигателя в карточке лота; группировка в поиске

Владелец, 13.11: «При нажатии на карточку аукциона не видно тип двигателя. И при поиске авто в общем списке сгруппируй».

## 1. Тип двигателя (сделано в пакете, НЕ установлено)
Страница video/korea.html, окно лота: строка «Двигун» = объём + тип: «2 996 см³ · бензин» (uk/ru/ka:
бензин, дизель, гібрид, електро, газ (LPG), водень). Нет типа — только объём, как сейчас.

Причина: сборщик читал «Fuel» со страницы лота только для бегущей строки; в lots.json его не было.
Пакет cloud/korea_engine_001; сборщик korea_auction = сборщик cloud/korea_tile_001 (KOREA-TILE, поверх установленного KOREA-TIME R3) + правки ниже:
- korea_auction/fuel.py — новый: текст «Fuel» → ключ типа (перенесён из ticker.py без изменений; ticker берёт его отсюда);
- prices.py — кэш страниц лота хранит fuel; записи без fuel перечитываются один раз (≈2100 лотов, 600 за запуск → 4 часовых прогона);
- public.py — lots.json: поле fuel (ключ);
- engine_page.py — 3 точечные правки video/korea.html (подписи типов, функция engine(l), строка «Двигун»).
Тесты: test_engine_page 4/4, korea_auction 50/50. Браузер (iPhone 13, живая страница + lots.json с fuel): «2 996 см³ · бензин»,
«3 470 см³ · дизель», без типа — «3 470 см³». Снимок cloud/photos/KOREA-ENGINE-001.png.
Установка: владелец 13.11 «4. Да» — одной устан## 2. Группировка в поиске (владелец: «чтоб было удобно покупателю», «3. Да»)
- model_groups.py — правка video/korea.html: при «Усі марки» список «Модель» разбит по маркам (<optgroup> «Hyundai», под ним
  «Sonata», «Tucson»…; значение — полное название, фильтр не меняется). При выбранной марке — как было.
- collect.py MODEL_FIXES — опечатки аукциона: Mornig → Morning, Mohavi → Mohave (одна модель — одна строка в поиске).
Проверка в браузере (iPhone 13): 31 группа, «Sonata» → 103 авто, марка Kia → 28 моделей без групп, назад «Усі марки» → 31 группа.
Тесты: test_model_groups 2/2, test_engine_page 4/4, korea_auction 55/55 (52 KOREA-TILE + 3 свои).

## 3. Установка (координатор 07:02 UTC: отдельно, сразу после KOREA-TILE; «да» владельца — здесь, «4. Да», и в чате 23 «1 да 2 да»)
Установочный пакет cloud/korea_engine_001 (по образцу korea_tile_001 #1470): база — сборщик, как его ставит KOREA-TILE-INSTALL
(хеши cloud/korea_tile_001/korea_auction); меняются fuel (новый), prices, public, collect, ticker + video/korea.html
(model_groups.build(engine_page.build(живая))). Образец страницы — живая korea.html после KOREA-RU. Тесты: deployment, release,
engine_page, model_groups, korea_auction — OK. Заявка tasks/requests/KOREA-ENGINE-PREFLIGHT-20261113.json записана, НЕ запущена.
Порядок: «твоя очередь» → если сборщик плашки установлен с другими хешами — пересобрать → launch preview → install → проверка живой korea.html.
