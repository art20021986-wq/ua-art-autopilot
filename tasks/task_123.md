# Task 123 — automatic site vehicle counters

User request, 2026-09-10: correct homepage 16 to the actual 18 published vehicles and keep vehicle totals/stages correct for subsequent publication, removal and stage changes.

Cause: old homepage script reads the inner `data-ua-card` marker but ignores its `data-category`. It consequently retained stale static counts. Catalog itself correctly contains UA-0001 through UA-0018 (18, stages 5/1/8/4); UA-0019 remains unpublished.

Implementation: `cloud/site_counters_123/`. Supersedes the uninstalled total-only proposal in `cloud/home_total_auto/`. Shared parser deduplicates vehicle IDs, recognizes current and legacy stage attributes, validates both catalog copies, and updates homepage RU/UK totals and stage labels. Existing catalog filter scripts/layout remain intact. Publisher hook updates counters within the existing lock and rollback transaction; snapshots additionally retain homepage files. Existing historical snapshots remain compatible. No database, vehicle content, media or CRM-folder changes.

Validation: 15 Python tests pass (including installer hash guards, rollback, publication snapshot restoration, 18→19→18 and stage changes). Node DOM-fixture tests pass for identity deduplication, aliases, invalid/empty data and RU/UK plurals. Empty catalog handling is tested in the counter layer; the existing publication design guard still disallows publishing an empty catalog. No real UA-0019 publication was performed.

Live deployment: 2026-09-10 11:54:10 UTC, PythonAnywhere native console. Preflight passed the existing golden-layout validator for both catalogs. Installer returned INSTALLED. Homepage browser then showed total 18 and stages 5/1/8/4 in Russian. Final language/filter/restart verification is being completed.

Backup: `/home/Carix/backups/site_counters_123/20260910T115410Z`.

Hashes:
- Installer: `9093496227acdfe84481c1a38020b46a7cbe9c8a6d81dc2d10a215cc99f0f20a`
- Core: `500ca67145faa38ca9f72ac6da85e2a7d1c351f8f2fcca4a2edeb34c22734c23`
- Publisher before: `ce6bd00338fbdc38b91f9554ea7baab3b8e921ffe6c1035aa4aba0186e2b549d`
- Publisher after: `4c293b9197810477922cbd46197a5a6f19a1e62736c421dd9cbf613b7cb0b5df`
- Homepage before: `3a8869b4da2fe58898a1237c0fea1b09d45dea80f7c61ab855c0d3a1cf739f8d`
- Homepage after: `1c5d0bbdd802af5dda2571be76e10773472380c7e473e3cc3c9f10611e1f53e3`
- Both catalogs unchanged: `e4c4379118f37c58b7eddfc3d1992f7fa62909205bf6cf063b44c01b22e8bdc8`

Rollback: run the same installer with `--rollback /home/Carix/backups/site_counters_123/20260910T115410Z`, then restart existing task 266084. Restore refuses intervening edits. No HALT/workflow changes.
