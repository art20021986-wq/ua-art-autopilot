# Latest status — TASK116

**Updated:** 2026-09-07  
**Contract:** `UA-ART-CRM-SPEC-PUBLISH-RECOVERY-001` v1.0

- Документационный execution package A–F подготовлен.
- Изменения runtime Python/Production: `0`.
- Production не вызывался и не изменялся этим шагом.
- Локальная candidate-матрица: 14/14 PASS, `PREVIEW_ONLY`; это **не Gate B**.
- `evidence/gate_b_local.json` обновлён свежим manifest-bound результатом;
  `gate_b_eligible=false`, `production_eligible=false`.
- Remote Gate A: `PARTIAL`. Получена read-only копия фактической CRM с
  `quick_check=ok`; точная строка `UA-0017` существует, `published=0`,
  `publish_pending=0`, дополнительная спецификация `0/10`.
- Gate B: `NOT_RUN / NOT_ELIGIBLE`.
- Public read-only observation: каталог показывает 16 карточек
  `UA-0001..UA-0016`; ссылки `UA-0017` нет, прямой адрес `UA-0017.html`
  перенаправляет на главную. Это не заменяет CRM/server Gate A.
- Аудит CRM подтверждает две неудачные попытки: в каждой `published` сначала
  переключался `0->1`, затем через 1–2 секунды откатывался `1->0`. Candidate
  блокирует этот временный publish-before-validation путь.
- Candidate подготовлен в отдельной ветке
  `codex/ua-art-crm-spec-publish-recovery-001`; точный head подтверждается
  GitHub evidence, а не Production-root.
- Exact VIN `UA-0017` пока `UNKNOWN`; использовать VIN `UA-0002` запрещено.
- Выпуск `UA-0017`: `BLOCKED`; текущее Production-состояние:
  `UNKNOWN_REMOTE_NOT_OBSERVED`.
- Production gate: `CLOSED`.

Следующий безопасный шаг: получить exact VIN из CRM read-only, выполнить
`remote_gate_a.py`, получить
фактический remote baseline, затем прогнать Gate B на свежих изолированных
копиях и передать владельцу отдельный отчёт.

Только после verified Gate B допустима отдельная точная команда владельца:

`ПУБЛИКОВАТЬ UA-0017`
