# CRM-VIN4-TITLE-001

Production transaction for adding the last four normalized VIN characters to
all current and future UA ART CRM car titles.

The transaction is restricted to `cars_ui.py`. It performs a read-only SQLite
audit, deterministic in-memory canary, timestamped backup, atomic install,
exact launcher restart, immediate and delayed postchecks, and automatic
rollback on any failure. Database, website and media writes are forbidden.
