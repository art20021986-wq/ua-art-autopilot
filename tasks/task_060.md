# TASK 060 — P0: AI MUST PARSE, NEVER HAND TO STAFF

OWNER APPROVAL: «В работу»
MODE: IMPLEMENT_AND_INSTALL
MAX_ROUNDS: 1
TOKEN_MODE: MINIMUM; one model call; JSON only; no second review or long report.

LIVE ACCEPTANCE FAILURE after TASK 059 installation (2026-08-28, 12:30 ICT, inbox #126):
- «Передал менеджеру» / «менеджеров в системе нет»
- «За 7 секунд поля CRM не найдены»
The visible screenshot contains Kia K5 2018, $11 400, 510 720 грн, 198 тыс. км, LPG 2.0, automatic, VIN KNAGU416BKA324445.

REQUIRED FIX:
1. Text, photo/screenshot, image-document and voice are parsed by AI automatically. Never route owner intake to a manager and never show manager messages.
2. Accept only keys present at runtime in `ai_filter.ALLOWED`; ignore every other value.
3. Normalize supported AI results: nested `fields[key].value`, scalar `fields[key]`, and flat allowed-key JSON. Missing fields must not reject readable fields.
4. One vision request, `max_tokens <= 500`, no second AI review. Deadlines: photo <=7 s, text <=2 s, voice <=10 s.
5. If at least one allowed field is found, show the CRM preview immediately with `✅ Разместить`. Do not auto-save, rebuild the site, add the source screenshot to the gallery, or publish a card.
6. Install only the minimal bot patch with backup/atomic rollback, restart the bot, and record evidence. Do not publish UA-0010.

ACCEPTANCE:
- This exact case produces a preview containing every readable allowed CRM field, with no manager message.
- Missing/unknown fields are ignored; partial result succeeds.
- Before `✅ Разместить`: CRM DB and site unchanged.
- Deliver only a short PASS/FAIL report and installation receipt.
