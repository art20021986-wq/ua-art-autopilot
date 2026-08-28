# TASK 069 — CRM-CONTAINER-KYIV-DAYS-001 v1.0 — FINAL REPORT

STATUS: **GATE A PASS · READY FOR SEPARATE PRODUCTION APPROVAL**

## Live read-only audit

- Current CRM cards: 11 (UA-0001…UA-0011).
- UA-0011: id=18, status=`sea_loaded`, `sea_container=NULL`, `eta_manual=NULL`, `days_to_kyiv=NULL`.
- SQLite: `PRAGMA quick_check=ok`.
- Live `konteyner.py`: SHA-256 `2d56a970fb76c782f0d5caebd65b6a7ffd44fd3ad1278a775bf641cffd39080d`.

## Proven cause

1. `prinyat()` removes `cont_wait` **before** the database write succeeds.
2. On write/read failure the input context is therefore lost.
3. The existing read-back is shown to the user but is not compared with the requested value.
4. The only existing days button is labelled «Дни до прибытия» inside the secondary container screen; the post-stage screen shown by the owner has no days button.

## Isolated fix

Exactly three functions change: `_ekran`, `prinyat`, `posle_statusa`.

- Keep `cont_wait` until DB read-back exactly equals the normalized container number.
- On mismatch: keep waiting and show an explicit retry message.
- On success: `✅ Контейнер сохранён: <номер>`.
- Replace the old days button with `⏱ Количество дней до Киева`.
- Show the same action in the post-stage prompt.
- Route both buttons to the existing tested handler `car_setf:<id>:eta_days`, which stores `eta_manual` and `days_to_kyiv`.
- No changes to cards, prices, stages, photos, videos, diagnostics, publication, or generators.

## Gate A evidence

- Source hash guard: PASS.
- Python compile: PASS.
- Only expected functions changed: PASS.
- One button per screen: PASS.
- Existing ETA handler route: PASS.
- Wait clear after read-back: PASS.
- Exact success reply: PASS.
- Runtime LLM tokens: 0.
- Candidate SHA-256: `a916266016d4ff0551e99bd74b5eb295e3c69babe2f6b7eec7f218d69a0de64b`.

Production/CRM writes and service reloads: **NO**. Gate B requires separate written owner approval.
