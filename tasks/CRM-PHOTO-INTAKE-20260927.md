# CRM photo creates and fills a draft

Requested by the owner: automatically create a new card from the supplied photo, then fill its form from explicitly supplied information only. Keep scope minimal, use existing dependencies, small modules and checked official practices.

Scope: photo and labelled-text intake for the owner; durable source admission; correct grouped numeric values; explicit field whitelist; atomic draft creation and blank-field filling; duplicate VIN/message protection. Existing media and field editors remain routed as before. No source-derived guessing, no pricing/auction fields, no site publication, no CRM data migration.

Implementation and verification: `cloud/crm_photo_intake_001/README.md`.

Owner authorization: current request explicitly asks to implement this behavior. Installation changes source code only through main Actions. Existing backup, rollback, health and transaction gates remain mandatory.
