# ADS-AWTAG-001 — тег конверсий Google Ads на сайте

Владелец 27.11 (~08:25Z «Да, поставь все как советует Google»): рекомендация Google «Завершите настройку отслеживания
конверсий». Шаг 1 (ADS-AWTAG-20261127, cloud/ads_awtag_001): действие WEBPAGE «Заявка з сайту (тег Google Ads)», secondary,
чтение AW-id и send_to. Шаг 2: общий блок ua_google_tag.py → V2: gtag config AW-… и conversion при каждом generate_lead
(обёртка gtag ловит и quick-lead.js); замена V1-блока на всех страницах; CRITICAL, превью → «да» → установка по очереди.
Шаг 3: после первых записей — тег primary, импорт GA4 secondary; enhanced conversions (условия принимаются в кабинете).
