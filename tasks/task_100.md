# TASK 100 — HOME LIVE COUNTERS + WHATSAPP OPACITY v1.0

OWNER_APPROVED: YES
APPROVED_AT_UTC: 2026-08-31T07:46:42Z

Команда владельца по live-сайту: «Кнопка вотс сделайте ее прозрачнее на 10%. Цифры авто не сходятся. Дополнение».

## Scope
1. Исправить главную страницу так, чтобы количество автомобилей и четыре этапных счётчика всегда вычислялись из текущих published-карточек CRM и совпадали с каталогом.
2. Запрещён hardcode total=13 или любого будущего total. Инвариант: total == Kyiv + Georgia + Sea + Korea == unique published cards == catalog cards.
3. Текущий acceptance gate: published total должен быть не меньше 16; фактическое распределение по этапам брать только из CRM/catalog, не угадывать.
4. Плавающую круглую кнопку WhatsApp сделать на 10% прозрачнее: opacity=0.90. Менять только floating/fixed WhatsApp control, не обычные текстовые WhatsApp-ссылки.
5. Сохранить размеры, позицию, кликабельность, safe-area и существующий дизайн кнопки.

## Root cause, подтверждённый аудитом
- TASK093 production controller/workflow был зафиксирован на историческом snapshot 13 / 3 / 1 / 7 / 2.
- TASK095 также содержит исторические EXPECTED_IDS UA-0001..UA-0013 и EXPECTED_COUNTS total=13.
- После появления UA-0014..UA-0016 каталог обновился, а homepage-counter contract остался привязан к 13.
- Исправление должно быть динамическим и не ломаться на UA-0017+.

## Safety
- Перед записью: read-only CRM quick_check, snapshot counts/IDs, сравнение CRM == catalog.
- CRM write: FORBIDDEN.
- Media write: FORBIDDEN.
- Card/catalog content write: FORBIDDEN для TASK100; разрешены только /video/index.html и, если совместим, /site/index.html.
- Backup каждого изменяемого homepage-файла.
- Atomic replace + production writer lock + rollback при любой ошибке.
- Не вмешиваться в TASK096 data-enrichment.

## Definition of Done
- homepage total == catalog total == CRM published total;
- сумма четырёх этапов == total;
- никаких hardcoded 13 в новой логике;
- WhatsApp floating button opacity 0.90;
- CRM SHA до/после одинаков;
- public cache-busted homepage показывает новые счётчики;
- rollback manifest/evidence сохранён;
- PASS только после public verification.
