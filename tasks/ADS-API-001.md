# ADS-API-001 — подключение автопилота к Google Ads через официальный API

Владелец, 25.11: «Да» — Claude сам настраивает рекламу; всё, что тратит деньги (включение, бюджет, ставки) —
только после «да» владельца в чате. Оплата (физлицо, карта), пополнение и проверка рекламодателя — владелец.
Рекламный аккаунт 468-074-7874 (UAH, Київ), связан с GA4 «UA ART» 560695713 (25.11).

## Шаги
1. Владелец: управляющий аккаунт Google Ads (MCC) на той же почте; привязать 468-074-7874.
2. Владелец: в MCC «Центр API» → заявка на developer token (Basic access). Ответы — ниже.
3. Claude: в проекте `uaart-autopilot` включить Google Ads API, OAuth-клиент (тип «Веб»/«Desktop»).
4. Владелец: один раз «Разрешить» (scope adwords); refresh token — секрет сервера (не репозиторий, не чат).
5. Claude: пакет `cloud/ads_api_001` (только чтение: отчёт) → затем кампания в статусе «Приостановлена» →
   включение и бюджет — по «да».

## Ответы для заявки на developer token
- Company name: UA ART COMPANY LLC; website: https://www.uaart.com.ua
- Business model: we advertise our own business only (car import from South Korea to Ukraine); single Google Ads
  account 468-074-7874 under our own manager account; no clients, no agency services.
- Use case: internal tool to create and manage our own Search campaigns (keywords, negative keywords, ads, budgets
  after owner approval) and to read daily performance reports (campaign, keyword, search terms, conversions).
- API services: Campaign management and Reporting. No access for third parties. Tool design: server-side script,
  OAuth for our own user, changes reviewed by the business owner before applying.
