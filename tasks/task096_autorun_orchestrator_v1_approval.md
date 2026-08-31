# TASK096-AUTORUN-ORCHESTRATOR v1.0
OWNER_APPROVED: YES
MAX_RECOVERY_ATTEMPTS: 10
PRODUCTION_AUTHORIZED: NO
LIVE_CRM_WRITE_AUTHORIZED: NO
BOT_WRITE_AUTHORIZED: NO
SITE_WRITE_AUTHORIZED: NO

Goal: replace manual stage-by-stage triggering with one checkpointed state-machine. Business COMPLETE is allowed only after 16/16 audit + semantic dedup + safety PASS. Workflow success alone is not business completion.

Required lifecycle:
BACKUP -> SANDBOX -> TESTS -> UA0015_CANARY -> SOURCE_EXPANSION -> ENRICH_16 -> DEDUP_16 -> VERIFY_16 -> SAFETY_AUDIT -> REPORT -> COMPLETE

Rules:
- Up to 10 recovery attempts.
- Single-instance lock.
- Resume from checkpoint after runner interruption.
- Transient failure => retry bounded stage.
- Deterministic code/config failure => repair-required state, no blind loop.
- Safety failure => HARD_STOP.
- Production/live CRM/bot/site writes forbidden.
- Purchase/auction/cost/wholesale/margin/markup data forbidden.
