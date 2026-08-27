# TASK 037 — BOT-LOGISTICS-001 phase A: единый центр этапа и доставки

## Решение владельца

Централизовать управление логистикой автомобиля в BOT CRM.

Для UA-0006 задан номер контейнера:

```text
ONEYSELGF1046602
```

Скриншот показывает ответ бота «Записано.», но подтверждением считается только повторное чтение из `crm.db`.

Единственная входная кнопка:

```text
🚢 Этапы и доставка
```

Она должна быть доступна:
1. В главном меню BOT CRM: выбрать автомобиль и открыть единый logistics hub.
2. В редактировании карточки UA-XXXX: открыть тот же hub сразу для выбранного автомобиля.

В hub показываются и меняются:
- этап;
- номер контейнера;
- дата отправления;
- дней до прибытия;
- расчётная дата прибытия (ETA).

Не придумывать отсутствующие дату/дни; показывать «не указано».

## Safety boundary

Phase A only: read-only discovery, candidate patch, offline tests and Gate A. Work only under `cloud/bot_logistics/`, plus required `cloud/latest_status.md` and `cloud/owner_reply.md`.

Do not:
- change Production, bot, `crm.db`, site, cards, generators, WSGI, processes or scheduled tasks;
- execute Gate B;
- run SQL writes/DDL on the real DB;
- publish UA-0009;
- mass-regenerate cards;
- touch `cloud/crm_speed_optimization/`;
- modify `tasks/`;
- use network in tests;
- expose credentials, tokens, PII or other CRM row values.

Markers:

```text
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
UA_0009_PUBLISHED: NO
```

Real source/DB writes are CRITICAL and require a separate phase B after verified Gate A and separate owner approval.

## 1. Read-only production discovery probe

Create a safe probe for PythonAnywhere safe inbox. Exact whitelist only:

- `/home/Carix/cars_ui.py`
- `/home/Carix/team_bot.py`
- `/home/Carix/avtoperedacha.py`
- `/home/Carix/db.py`
- `/home/Carix/run_all.py`
- `/home/Carix/start_safe.py`
- `/home/Carix/crm.db`

Never recursively scan `/home/Carix`.

Find exact source functions, callback/state flow and SQLite schema tied to:
- `Срок доставки`;
- `📦 Номер и дата контейнера` / `Номер и дата контейнера`;
- `Дней до прибытия`;
- `Номер контейнера`;
- existing stage buttons.

SQLite discovery requirements:
- URI `mode=ro`;
- `PRAGMA query_only=ON`;
- `PRAGMA quick_check`;
- prove exactly one UA-0006 row;
- read the UA-0006 container and compare to `ONEYSELGF1046602`;
- prove DB SHA-256 identical before/after;
- no other CRM values and no PII in output;
- fail closed on ambiguous schema/row, lock, malformed DB, symlink, hard link or unstable identity.

Output one of:
- `UA0006_CONTAINER_STATUS: ALREADY_CORRECT`;
- `UA0006_CONTAINER_STATUS: NEEDS_EXACT_UPDATE`.

Do not update it in phase A.

Return only bounded, sanitized source snippets around the UI anchors, with file/function/callback identities and SHA-256 evidence. Do not emit tokens or secrets.

## 2. Canonical UX

Universal for UA-0001…UA-XXXX. No UA-0006-only UI hardcode.

### Exactly two entry locations, one implementation

- Main menu: exactly one `🚢 Этапы и доставка`; then normal car selection; then hub.
- Card editor: exactly one `🚢 Этапы и доставка`; selected UA-ID goes directly to hub.
- Both must call the same canonical hub handler and persistence functions.

### Hub content/actions

Show freshly read:
- UA-ID;
- current stage;
- container;
- departure date;
- days to arrival;
- ETA.

Internal hub actions may be:
- `Этап`;
- `Контейнер и дата`;
- `Дней до прибытия`;
- context-correct Back.

These are actions inside the one central hub, not duplicate entry points elsewhere.

### Remove old duplicate entries only

From the old stage menu remove:
- `Срок доставки`;
- `📦 Номер и дата контейнера` / `Номер и дата контейнера`.

From the old card editor remove:
- `Дней до прибытия`;
- `Номер контейнера`.

Replace those card-editor controls with one `🚢 Этапы и доставка`.

Do not delete capabilities or stored data; move them to the hub.

## 3. Persistence behavior

### Container

- trim + uppercase;
- accept alphanumeric 7–32 chars;
- `ONEYSELGF1046602` must pass; do not enforce only 4 letters + 7 digits;
- reject internal whitespace, control characters and unproven punctuation;
- preview old/new before confirmation;
- parameterized SQL; exactly selected UA-ID; rowcount == 1;
- after COMMIT close write connection, then re-open read-only and compare exact saved value;
- show «Записано» only after exact read-back;
- rollback and no success message on any failure;
- same-value update is idempotent.

### Container + departure date

One flow can edit container, departure date, preview, Save/Cancel. Either field may remain unchanged; never silently clear the other.

### Days + ETA

- integer; use proven current range, otherwise 0–365;
- one canonical ETA function from saved departure date + saved days;
- do not create competing stored derived values if current schema stores primary values;
- stage change must not clear container/date/days;
- any field change must preserve all untouched fields;
- every hub render uses fresh DB reads.

## 4. Prepared, non-executed Gate B

Create a fail-closed installer but do not execute it.

It must:
- use only discovery-proven source paths/anchors;
- create timestamped backups of source files and a consistent SQLite backup via SQLite backup API;
- write manifest with SHA-256/mode/size/mtime_ns before changes;
- refuse if live SHA differs from Gate A;
- compile and test candidates before replacement;
- atomic-replace source files only;
- update at most one UA-0006 row, and only if current value differs;
- quick_check after transaction and exact read-back of `ONEYSELGF1046602`;
- prove all other bounded CRM rows unchanged without outputting their contents;
- rollback source and DB on any failure;
- not restart bot processes or reload WSGI;
- end `WAITING_OWNER_APPROVAL`.

## 5. Mandatory offline tests

Temporary dirs, fixture SQLite, fake Telegram UI only. No network or `/home/Carix`.

Prove:
1. Main menu has exactly one hub entry.
2. Card editor has exactly one hub entry.
3. Both delegate to one hub.
4. Old duplicate entries are absent from old menus.
5. Hub exposes stage, container+date, days.
6. Correct context back navigation.
7. Telegram callback length/uniqueness.
8. `ONEYSELGF1046602` accepted intact.
9. Invalid container rejected.
10. Exactly one selected row updated and exact read-back.
11. Same-value idempotence.
12. rowcount/failure rollback; never false «Записано».
13. Stage edit preserves container/date/days.
14. One-field edit preserves all others.
15. Deterministic ETA.
16. quick_check before/after.
17. UA-0001…UA-0008 unchanged except the explicitly allowed UA-0006 container field in Gate B fixture.
18. UA-0009 preserved and not published.
19. No photo/video/media calls added to admin routes.
20. Candidates compile.
21. Ten transforms have identical candidate/diff hashes.
22. Backup/manifest/tamper/rollback PASS.
23. No PII/tokens/other row values in outputs.

## 6. UA-0009 mandatory conclusion

Read-only preservation only:
- before/after unchanged;
- never publish;
- state whether the candidate remains universal for UA-0009/future cards;
- do not claim `UA_0009_READY: YES` without complete proof.

## Deliverables

Exactly:
- `cloud/bot_logistics/README.md`
- `cloud/bot_logistics/bot_logistics_discovery.py`
- `cloud/bot_logistics/bot_logistics_transform.py`
- `cloud/bot_logistics/bot_logistics_gate_b.py`
- `cloud/bot_logistics/test_bot_logistics.py`
- `cloud/bot_logistics/TASK_037_REPORT.md`
- `cloud/latest_status.md`
- `cloud/owner_reply.md`

No archives, DB binaries or production snapshots in GitHub.

## Expected phase-A finish

If exact anchors/schema are unavailable without PythonAnywhere discovery, return `WAITING_PYTHONANYWHERE_READ_ONLY_DISCOVERY` with exactly one safe file and one command. Never invent PASS.

If all offline work is ready:

```text
TASK_ID: task_037
CLAUDE_STATUS: DONE
CURRENT_ACTION: BOT_LOGISTICS_GATE_A_READY
PRODUCTION_TOUCHED: NO
CRM_TOUCHED: NO
CRM_DB_WRITTEN: NO
GATE_B_EXECUTED: NO
OWNER_ACTION_REQUIRED: YES
OWNER_QUESTION: CRITICAL APPROVAL — apply verified BOT-LOGISTICS-001 patch and, only if needed, set ONEYSELGF1046602 for UA-0006? Answer APPROVE or CANCEL.
NEXT_FOR_CHATGPT: independently compile/run offline tests, audit evidence, then request the single owner approval only if all PASS.
```
