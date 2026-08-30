# TASK 096 — DATA-ENRICHMENT SANDBOX — OWNER APPROVAL

OWNER_APPROVED: YES
APPROVED_AT_UTC: 2026-08-30T19:29:05Z
CONTRACT_ID: TECH-SPEC-AI-CRM-017-V3.0-TASK096-DATA-ENRICHMENT

## Exact approved command

> УТВЕРЖДАЮ TASK 096 DATA-ENRICHMENT SANDBOX. СНАЧАЛА ЗАПУСТИТЬ UA‑0015 КАК DATA-CANARY. ПОСЛЕ PASS АВТОМАТИЧЕСКИ ОБРАБОТАТЬ UA‑0001…UA‑0016. ОСНОВНЫЕ ПОЛЯ CRM, РАБОЧУЮ БАЗУ, БОТА, САЙТ И PRODUCTION НЕ ИЗМЕНЯТЬ. ЦЕНУ ЗАКУПКИ НЕ ИЗВЛЕКАТЬ И НЕ СОХРАНЯТЬ. ПРИ СБОЕ — ДО ТРЁХ АВТОПЕРЕЗАПУСКОВ ТОЛЬКО УПАВШЕГО ЭТАПА. ПОСЛЕ ВЫПОЛНЕНИЯ — ПОЛНЫЙ ОТЧЁТ И ПРЕДПРОСМОТР UA‑0015.

## Hard boundaries

- First gate: UA-0015 only.
- Batch gate: UA-0001 through UA-0016 only after UA-0015 PASS.
- Live `/home/Carix/crm.db`: read-only verification only; no writes.
- Sandbox database only: `/home/Carix/autopilot_inbox/cloud/task_096_tech_spec_ai_crm/sandbox/`.
- Bot, site, generator, public paths and production: no changes.
- Purchase, auction, wholesale, dealer and cost prices: do not extract, store, log, upload or display.
- External source URLs remain internal metadata and must not appear in the client preview.
- Automatic publication and service restarts are forbidden.
- Retry policy: maximum three retries of the failed stage; completed stages are reused.
- Production remains blocked pending a separate explicit owner command.
