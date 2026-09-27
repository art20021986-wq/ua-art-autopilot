# Explicit photo intake

Owner request (2026-09-27): a specs photo creates a saved CRM draft and subsequent explicit data fills its form. Copy only information present in the source. No guessed manufacturer/model/year, auction details or automatic public publication.

The old screenshot path split `109,353 km` into `109`, inferred a production year from registration date, missed capacity/color, and returned an unsaved preview.

The runtime change is three modules and one registration call in `team_bot.py`:
- `crm_explicit_fields.py`: labelled rows, validation, existing CRM dictionaries. Registration date is not a production year. Conflicting values are omitted.
- `crm_intake_store.py`: existing queued SQLite connection, one transaction for VIN lookup, draft creation/fill, inbox link and audit. Replayed messages and known VINs do not create duplicates. Existing nonempty, published and archived data is preserved.
- `crm_photo_intake.py`: existing local Tesseract/Pillow, bounded full-page OCR in a worker thread, background Telegram task and ordered follow-up messages. Staff permissions, stop control and explicit editors retain priority. Source messages are recorded before acknowledgement. No new dependencies or outside service.

A new photo needs an unambiguous full VIN. Text follow-ups use explicit labels (for example `Марка: Kia` and `Модель: K5`) and fill the active intake draft. Unknown fields remain empty. Photos used as data sources are kept in the inbox, not in the vehicle gallery. A process interruption leaves its source in the inbox; resending safely retries by VIN.

Validation: 43 passing local tests, including transaction rollback, concurrent duplicate submissions, message replay, follow-up ordering, navigation and source-only installation/recovery fault injection. The attached real photo yields six fields: VIN, 109353 km, 1999 cc, black, automatic and LPG; registration and auction fields are omitted. Local OCR timing is not a production latency promise.

Deployment follows the existing source-only main Actions lifecycle, with an isolated package prefix, pinned source/dependency hashes, read-only remote preview, backup, writer locks, bot pause/resume, exact file verification, preservation checks, and source-only rollback. No CRM migration or test record is written. Lifecycle helpers retain the established release pattern so the existing deployed publisher is not refactored.

Official references checked:
- https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html
- https://docs.python.org/3.10/library/asyncio-task.html#asyncio.to_thread
- https://docs.python-telegram-bot.org/en/v21.1/telegram.ext.application.html#telegram.ext.Application.create_task
- https://www.sqlite.org/lang_transaction.html
- https://core.telegram.org/bots/api

Installation status is tracked in the deployment receipts; local tests are not proof of production installation or an end-to-end Telegram message.
