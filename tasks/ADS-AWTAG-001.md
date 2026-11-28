# ADS-AWTAG-001 — тег конверсий Google Ads на сайте

Владелец 27.11 (~08:25Z «Да, поставь все как советует Google»): рекомендация Google «Завершите настройку отслеживания
конверсий». Шаг 1 (ADS-AWTAG-20261127, cloud/ads_awtag_001): действие WEBPAGE «Заявка з сайту (тег Google Ads)», secondary,
чтение AW-id и send_to. Шаг 2: общий блок ua_google_tag.py → V2: gtag config AW-… и conversion при каждом generate_lead
(обёртка gtag ловит и quick-lead.js); замена V1-блока на всех страницах; CRITICAL, превью → «да» → установка по очереди.
Шаг 3: после первых записей — тег primary, импорт GA4 secondary; enhanced conversions (условия принимаются в кабинете).

## Шаг 2 — пакет готов (2026-11-28)
Пакет `cloud/ads_awtag_site_001` (ADS-AWTAG-SITE-PREFLIGHT-20261128 / ADS-AWTAG-SITE-INSTALL-20261128):
`ua_google_tag.py` V1 (f5f0a304) → V2 — GA4 как было, `config AW-18537441937`, одна конверсия
`AW-18537441937/fvkWCIT9vsAdEJHVq4dF` на каждый generate_lead (обёртка gtag, quick-lead.js тоже); блок V1 → V2 на всех
страницах с ним, больше ничего. Без enhanced conversions и данных клиента. Проверки: test_release 13, test_google_tag 3
(Node), test_deployment 34. Не запущен: ждёт «Да» владельца и очереди координатора.
