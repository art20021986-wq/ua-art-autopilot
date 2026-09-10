# UA-ART-STAGE-SYNC-004 deployment report

Date: 2026-09-10 UTC
Status: current mismatch repaired; automatic reconciliation installed and registered.

## Confirmed incident

CRM already held ge_waiting for UA-0009 (row 15), UA-0010 (row 16), UA-0011 (row 18), UA-0012 (row 19), published=1.
All eight primary-page copies already had data-ua-stage-current=3.
Both catalogs still classified these IDs as sea/more. The active cars_ui.stage_set saved/read back CRM without invoking catalog synchronization.
The earlier task123 counter hook ran after catalog installation; it did not close this stage-change gap.

## Applied changes

At 12:59:35 UTC, the adapter changed exactly:
- /home/Carix/video/katalog.html
- /home/Carix/site/katalog.html
- /home/Carix/video/index.html

Final published counts: all=18, kiev=5, georgia=5, sea=4, korea=4.
UA-0019 remains unpublished. No database mutations were made by this repair.
Legacy /home/Carix/site/index.html has no modern counter markers and is preserved under the existing counter module contract.

HTML backup: /home/Carix/backups/stage_catalog_sync/20260910T125935Z-19694d2a
A prechange SHA-256 inventory covered 115 flat HTML files. Postcheck found only the three intended files changed; 112 remained byte-identical.
href/src/onclick/action attribute inventories in the three changed files match their preimages.

Runtime hook applied 13:01:29 UTC to /home/Carix/cars_ui.py only.
Backup: /home/Carix/backups/stage_sync_004/20260910T130129Z
Before SHA: 5d3a4972b5605b35c2e19e0021176206c2f18b09e75197edc9a725fcfa481ad6
After SHA: ea5e68c0cce1662808e95836f56f811ba56cbf825b09d2dae928bb1d35162205
Adapter SHA: c349d44821f92950234705d41507587c3ca2780dd750abda0028c060569a5beb

The handler invokes reconciliation in a thread after saved-stage verification. Only confirmed synchronization returns a completion message.
A 15-second job checks CRM/file signatures and skips unchanged verified input. Failed input is retried at most three times per unchanged signature; new owner data or late primary-page generation enables a new attempt.
The adapter uses the existing publication lock, validates all ID/stage/count sets, checks primary-page readiness, backs up only affected HTML, verifies writes and rolls back owned files on handled failure.
The website process was not restarted. The existing CRM task was restarted; both bots started at 13:07:22 UTC. The log confirms registration of ua-stage-catalog-sync-004. The installed hook SHA was verified after startup.

## Validation

11 local tests passed, including the four-car move, nonstage content preservation, idempotence, invalid data rejection, dry-run, rollback on write errors and concurrent CRM edits, primary-page readiness, and legacy homepage preservation.
An initial live dry-run rejected legacy homepage markup without writing public files. The adapter was corrected to follow the installed counter module contract; the subsequent live dry-run passed.
A post-apply reconciliation returned NOOP with 18 and 5/5/4/4.
Live browser checks:
- Georgia filter: 5 IDs, exactly UA-0001, UA-0009, UA-0010, UA-0011, UA-0012.
- Ferry filter: 4 IDs, exactly UA-0005, UA-0006, UA-0013, UA-0014.
- Korea filter: 4 IDs, exactly UA-0003, UA-0004, UA-0015, UA-0016.
- Kyiv filter: 5 IDs, exactly UA-0002, UA-0007, UA-0008, UA-0017, UA-0018.
- All filter: 18; navigation to the homepage works.
- Homepage RU and UA show 5/5/4/4 and total 18.

Limitations: no fabricated production stage changes were introduced for a test. A later real owner transition has not yet been observed end-to-end. The scheduler registration is confirmed; unchanged-state executions are deliberately quiet. Physical iPhone, mobile 5G and TikTok testing was not performed in this session.
