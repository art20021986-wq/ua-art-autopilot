# TASK 049 — ЕДИНЫЙ ЦЕНТР «ЭТАПЫ И ДОСТАВКА» В BOT CRM

OWNER REQUEST:

- Для UA-0006 использовать контейнер `ONEYSELGF1046602`; прежнее значение заменить только если оно отличается.
- Удалить отдельную кнопку «Срок доставки».
- Удалить отдельные входы «Сменить этап», «Дней до прибытия» и «Номер контейнера» из внешних меню.
- В карточке и в редакторе карточки оставить по одному входу `🚢 Этапы и доставка`.
- Внутри этого центра дать изменение этапа, номера контейнера и количества дней до прибытия.
- Все остальные поля редактора сохранить.
- Контейнер и срок всегда менять для уже выбранной карточки, без повторного выбора машины.

## Verified current state

Read-only discovery already proved exactly one UA-0006 row in `/home/Carix/crm.db`:

- table: `cars`
- identity column: `auto_number`
- container column: `sea_container`
- container status: `ALREADY_CORRECT`
- current exact value: `ONEYSELGF1046602`
- database SHA before/after discovery: identical

Therefore no database write is needed for UA-0006.

## Phase in this task

Build and execute Gate A only against an isolated candidate copy of `/home/Carix/cars_ui.py`.

Gate A may:

- read `/home/Carix/cars_ui.py` read-only;
- write only below `/home/Carix/autopilot_inbox`;
- create and compile a candidate copy;
- emit a bounded JSON receipt.

Gate A must not:

- replace or edit `/home/Carix/cars_ui.py`;
- write `crm.db` or any CRM table;
- restart/reload a bot, web app or process;
- publish UA-0009;
- execute Gate B.

## Required candidate behavior

### Card keyboard

- exactly one `🚢 Этапы и доставка` entry;
- no standalone `Сменить этап` entry;
- no standalone `Срок доставки` entry;
- unrelated card controls remain present.

### Card editor

- exactly one `🚢 Этапы и доставка` entry;
- `eta_days` and `sea_container` are removed from the generic `EDITABLE` grid;
- all unrelated editor fields remain byte-equivalent.

### Central hub

The hub displays current status, container, days remaining and calculated arrival date, and contains:

- `Сменить этап` → existing stage flow;
- `Номер контейнера` → existing selected-card field flow;
- `Количество дней` → existing selected-card ETA flow;
- origin-aware `← Назад` to card or editor.

The post-stage duplicate `Изменить срок доставки` button is removed. The ETA field label becomes `количество дней до прибытия`.

## Safety gate

The source transform is bound to the discovered source SHA-256:

`06e7da916ea36c4ffafef01c85f59a0574f06d3cdda24aa1f8c242175de726b7`

Any SHA mismatch, missing/duplicate exact anchor, compile failure or invariant failure must return `BLOCKED` and make no production change.

Finish Gate A with `WAITING_OWNER_APPROVAL`. Gate B requires a separate explicit owner reply `APPROVE` after the Gate A receipt is audited.

