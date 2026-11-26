# SEARCH-HOME-001 — установка A (сессия 40)

Задача: `tasks/SEARCH-HOME-001.md`; разведка и ответы владельца: `cloud/search_home_001/README.md`.
«Да» владельца (UTC 26.11): 12:19:10, 12:22:05, 12:30:58, 12:33:28.

Что ставит (основа — файлы после KOREA-TOP-TILE-INSTALL-20261126, сессия 34):
- `korea_auction/country_tabs.py` (новый) + `ticker.py`: вкладки Корея / Америка / Японія на плашке недели;
  подпись «🇰🇷 Оцінка стану — аукціони Кореї» над оценкой.
- `video/korea.html` (`offer_text.py`): плашка «Авто з усіх країн під ключ · послуга 600 $ за договором · інші витрати —
  за рахунками аукціонів і перевізників»; ru/korea.html пересобирает установленный ua_korea_ru.
- `video/korea/logistics.json` (`logistics_port.py`): порт Грузии 400 $ (итог шага 3 на главной 3 450 → 3 600 $).
- Новые: `video/usa.html` (`ua_usa_page.py`), `video/usa/usa-calc.js`, `video/usa/tariffs.json` (копия 26.11, 547 площадок),
  `usa_costs.py`, `usa_tariffs_sync.py` + ежедневная задача 02:17 UTC (сбор, если копии ≥ 6 дней).
Откат: прежние файлы, новые удаляются, задача США снимается. Главная не трогается.
Тесты: 126 OK (korea_auction, deployment, release, usa_calc). Фото: cloud/photos/40-A-*.png, 40-TICKER-TABS-*.png.
