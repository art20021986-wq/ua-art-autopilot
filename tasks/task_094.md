# TASK 094 — UA-WEB-DESIGN-ROLLBACK-035 v1.0

STATUS: OWNER APPROVED / P0 / PRODUCTION RESTORATION
AUTHORIZATION: OWNER_APPROVED_PRODUCTION
ISSUE: #35

## Owner directive

The owner explicitly approved `UA-WEB-DESIGN-ROLLBACK-035 v1.0` and ordered immediate restoration of the PREVIOUS APPROVED WEB DESIGN with every function preserved. This is not a redesign and not a counters-only task.

Required final state:

- PREVIOUS APPROVED WEB DESIGN restored 1:1 as far as verified preimages allow;
- the four stage blocks are visible at the top in this order: Kyiv, Georgia, Ferry, Korea;
- on mobile the approved vertical composition is restored: image above, stage/car description below, not the currently broken left-text/right-image split;
- the approved vehicle-card web design is restored, including typography, borders, spacing, images, CTA placement and responsive behavior;
- current live business data remains authoritative: 13 / 3 / 1 / 7 / 2;
- UA-0001 through UA-0013 remain present and accessible;
- UA-0011 remains published on Ferry;
- CRM, database rows, photographs, videos, VINs, prices and descriptions must not be rolled back or mutated.

## Incident evidence

TASK 093 changed `/home/Carix/video/index.html` and created this pre-write backup:

`/home/Carix/backups/task_093_home_counters/20260830T010212Z_7e621e5028`

Its recorded public preimage SHA-256 is:

`7e621e50282d240ab73ded3903c95490fc8145435061c69e49eca14c021910f4`

However, the owner reports that both the homepage/stage composition and vehicle-card layout are wrong. Therefore do not assume that rolling back TASK 093 alone is sufficient. Audit earlier bounded production backups and receipts, especially the TASK 086 catalog/stage operation, to identify the last verified approved presentation preimages for:

- `/home/Carix/video/index.html`
- `/home/Carix/video/katalog.html`
- any presentation-only CSS/JS files actually changed by the incident chain.

## Mandatory execution model

### Phase A — read-only forensic audit

1. Enumerate relevant TASK 086 and TASK 093 production receipts/manifests/backups.
2. Record current hashes for homepage, catalog and all candidate presentation assets.
3. Identify exactly which operation changed each visible layout.
4. Compare current files to candidate preimages structurally.
5. Select only a cryptographically verified preimage that contains the approved stage and card composition.
6. Produce a restore map: target path → selected backup → source SHA-256 → expected restored SHA-256.
7. Fail closed if the approved preimage cannot be proven. Do not invent or reconstruct a design from memory when a verified backup exists.

### Phase B — bounded production controller package

Prepare an executable, zero-LLM production controller under `cloud/task_094_web_design_rollback/` that:

1. uses `PYTHONANYWHERE_API_TOKEN` only through GitHub Actions secrets;
2. takes a fresh emergency backup of every target before write;
3. acquires `/home/Carix/.ua_art_production_writer.lock`;
4. verifies current hashes and all selected backup hashes before writing;
5. restores presentation files atomically;
6. preserves or re-applies current counts 13 / 3 / 1 / 7 / 2 without altering the approved layout;
7. never writes CRM/database/media;
8. verifies HTTP 200 and public cache-busted HTML twice, immediate and delayed;
9. verifies the four top stages and mobile vertical layout markers;
10. verifies all 13 catalog IDs and current stage distribution;
11. automatically rolls back to the fresh emergency backup on any failed invariant;
12. writes machine-readable production evidence and a concise owner report.

## Scope prohibitions

- No full-server rollback.
- No CRM write.
- No SQLite write.
- No media write, move, rename or deletion.
- No deletion of UA-0011, UA-0012 or UA-0013.
- No manual recreation when an exact preimage is available.
- No PASS based only on script exit code.
- No claim that GitHub Actions success means the public site is restored.

## Acceptance gate

The task is complete only when all are true:

- DESIGN = verified previous approved presentation;
- DATA = current production, 13 / 3 / 1 / 7 / 2;
- mobile stage blocks and vehicle cards use image-above/text-below composition;
- every card opens;
- CRM/media/database hashes are unchanged;
- public verification passes twice;
- evidence includes before/after hashes, backup paths, target list and rollback status.

## Progress reporting

Write factual checkpoints at 5% increments in the report only when the corresponding work is actually complete. Required sequence:

START → FORENSIC INVENTORY → PREIMAGE VERIFIED → RESTORE MAP → CONTROLLER TESTED → PRODUCTION BACKUP → ATOMIC RESTORE → PUBLIC CHECK 1 → PUBLIC CHECK 2 → PASS/FAIL.

## Owner approval text

`УТВЕРЖДАЮ UA-WEB-DESIGN-ROLLBACK-035 v1.0. НЕМЕДЛЕННО В PRODUCTION. ВЕРНУТЬ PREVIOUS APPROVED WEB DESIGN 1:1, СОХРАНИВ АКТУАЛЬНЫЕ ДАННЫЕ 13 / 3 / 1 / 7 / 2. BACKUP → RESTORE → CROSS-CHECK → PUBLIC VERIFY → AUTO-ROLLBACK ПРИ ОШИБКЕ.`

Claude stage may prepare and validate the bounded package. The actual production write must be performed only by the owner-authorized deterministic controller with evidence and automatic rollback.
