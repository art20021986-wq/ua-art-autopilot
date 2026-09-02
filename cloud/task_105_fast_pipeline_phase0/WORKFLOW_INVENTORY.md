# WORKFLOW INVENTORY — TASK105

Generated: `2026-09-01T10:32:43Z`
Total workflows: **129**

## Classification totals

| Class | Count |
|---|---:|
| KEEP | 4 |
| MERGE | 92 |
| ARCHIVE | 33 |
| DELETE_CANDIDATE | 0 |

## Target consolidation

| Target pipeline | Current workflows mapped |
|---|---:|
| `uaart_fast.yml` | 4 |
| `uaart_standard.yml` | 21 |
| `uaart_critical.yml` | 69 |
| `uaart_monitor.yml` | 2 |
| `uaart_backup.yml` | 27 |
| `uaart_rollback.yml` | 6 |
| `uaart_maintenance.yml` | 0 |

## Full inventory

| # | Workflow | Trigger | Concurrency | PA | AI | Prod | Queue | Retry | Owner gate | Class | Target |
|---:|---|---|---|:---:|:---:|:---:|:---:|:---:|:---:|---|---|
| 1 | `.github/workflows/claude_autopilot.yml` | workflow_dispatch | `claude-autopilot` | NO | YES | YES | NO | YES | YES | **KEEP** | `uaart_critical.yml` |
| 2 | `.github/workflows/ferry_wording_gate_a.yml` | workflow_dispatch, push | `ferry-wording-isolated-gate-a` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 3 | `.github/workflows/ferry_wording_gate_b.yml` | workflow_dispatch, push | `ferry-wording-task-063-approved-gate-b` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 4 | `.github/workflows/overnight_autopilot_production_dispatch.yml` | workflow_dispatch, workflow_run | `overnight-autopilot-production-dispatch` | NO | NO | YES | NO | NO | YES | **MERGE** | `uaart_critical.yml` |
| 5 | `.github/workflows/overnight_task099_transient_recovery.yml` | workflow_run | `overnight-task099-transient-recovery` | YES | NO | YES | NO | YES | NO | **ARCHIVE** | `uaart_rollback.yml` |
| 6 | `.github/workflows/owner_ua0011_full_card_gate_a.yml` | workflow_dispatch, push | `NONE` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 7 | `.github/workflows/owner_ua0011_korea_now_production.yml` | workflow_dispatch, push | `owner-ua0011-korea-now-20260829` | YES | NO | YES | YES | YES | YES | **ARCHIVE** | `uaart_backup.yml` |
| 8 | `.github/workflows/owner_ua0011_korea_slim_production.yml` | workflow_dispatch, push | `owner-ua0011-korea-slim-20260829` | YES | NO | YES | YES | YES | YES | **ARCHIVE** | `uaart_backup.yml` |
| 9 | `.github/workflows/pythonanywhere_sync.yml` | workflow_dispatch, workflow_run, push | `pythonanywhere-inbox-sync` | YES | NO | NO | NO | NO | YES | **KEEP** | `uaart_critical.yml` |
| 10 | `.github/workflows/safe_workflow_watchdog.yml` | workflow_dispatch, workflow_run, push, schedule | `safe-workflow-watchdog` | YES | NO | YES | NO | YES | YES | **KEEP** | `uaart_critical.yml` |
| 11 | `.github/workflows/seo-rehab-068-production.yml` | workflow_dispatch, push, pull_request | `seo-rehab-guard-068-production` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 12 | `.github/workflows/seo-watch-smoke.yml` | workflow_dispatch, push, pull_request | `NONE` | NO | NO | NO | NO | YES | YES | **KEEP** | `uaart_monitor.yml` |
| 13 | `.github/workflows/task037_discovery.yml` | workflow_dispatch, push | `task037-discovery-readonly` | YES | NO | NO | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 14 | `.github/workflows/task039_retry.yml` | workflow_dispatch, push | `task-039-pinned-safe-retry` | YES | YES | NO | NO | YES | YES | **ARCHIVE** | `uaart_critical.yml` |
| 15 | `.github/workflows/task039_safe_inbox_sync.yml` | workflow_dispatch, push | `task039-safe-inbox-sync` | YES | NO | NO | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 16 | `.github/workflows/task049_gate_a.yml` | workflow_dispatch, push | `task049-logistics-hub-gate-a` | YES | NO | NO | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 17 | `.github/workflows/task049_gate_b.yml` | workflow_dispatch, push | `task049-logistics-hub-gate-b` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 18 | `.github/workflows/task049_gate_b_preflight.yml` | workflow_dispatch, push | `task049-gate-b-readonly-preflight` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 19 | `.github/workflows/task058_crm_ocr_readonly.yml` | workflow_run | `task058-crm-ocr-readonly` | YES | NO | NO | NO | YES | NO | **MERGE** | `uaart_standard.yml` |
| 20 | `.github/workflows/task059_ai_fast_schema.yml` | workflow_run | `task059-ai-fast-schema` | YES | NO | YES | NO | YES | NO | **MERGE** | `uaart_critical.yml` |
| 21 | `.github/workflows/task060_install_token_free_ocr.yml` | workflow_dispatch, push | `task060-install-token-free-ocr` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 22 | `.github/workflows/task060_read_live_context.yml` | workflow_dispatch, push | `task060-read-live-context` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 23 | `.github/workflows/task060_runtime_capabilities.yml` | workflow_dispatch, push | `task060-runtime-capabilities` | YES | NO | NO | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 24 | `.github/workflows/task061_crm_ai_card.yml` | workflow_dispatch, push | `task061-crm-ai-card` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 25 | `.github/workflows/task062_crm_voice.yml` | workflow_dispatch, push | `task062-crm-voice` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 26 | `.github/workflows/task062_read_voice_context.yml` | workflow_dispatch, push | `task062-read-voice-context` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 27 | `.github/workflows/task064_crm_db_lock_hotfix.yml` | workflow_dispatch, push | `task064-crm-db-lock` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 28 | `.github/workflows/task064_diagnostics_permanent.yml` | workflow_dispatch, push | `task064-permanent-diagnostics-repair` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 29 | `.github/workflows/task064_emergency_crm_quiesce.yml` | workflow_dispatch, push | `task064-crm-db-lock` | YES | NO | NO | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 30 | `.github/workflows/task064_read_crm_lock_context.yml` | workflow_dispatch, push | `task064-crm-db-lock` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 31 | `.github/workflows/task064_trace_wrapper_probe.yml` | push | `NONE` | YES | NO | NO | NO | YES | NO | **MERGE** | `uaart_critical.yml` |
| 32 | `.github/workflows/task065_counter_v2_hotfix.yml` | push | `task065-crm-rehabilitation-v2` | YES | NO | NO | NO | YES | NO | **ARCHIVE** | `uaart_standard.yml` |
| 33 | `.github/workflows/task065_crm_photo_fastpath.yml` | push | `task065-crm-photo-fastpath` | YES | NO | YES | NO | YES | NO | **MERGE** | `uaart_critical.yml` |
| 34 | `.github/workflows/task065_photo_path_probe.yml` | push | `NONE` | YES | NO | NO | NO | YES | NO | **MERGE** | `uaart_standard.yml` |
| 35 | `.github/workflows/task065_ua0011_probe.yml` | push | `NONE` | YES | NO | NO | NO | YES | NO | **MERGE** | `uaart_standard.yml` |
| 36 | `.github/workflows/task065_voice_path_probe.yml` | push | `NONE` | YES | NO | NO | NO | YES | NO | **MERGE** | `uaart_standard.yml` |
| 37 | `.github/workflows/task066_stage_anchor_deploy.yml` | workflow_dispatch, push | `task066-stage-anchor-v1-1-deploy` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 38 | `.github/workflows/task066_stage_anchor_probe.yml` | workflow_dispatch, push | `task066-stage-anchor-probe` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 39 | `.github/workflows/task067_crm_online_guard_deploy.yml` | workflow_dispatch, push | `task067-crm-online-guard-v1-3-deploy` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 40 | `.github/workflows/task067_health_probe.yml` | workflow_dispatch, push | `NONE` | YES | NO | YES | NO | NO | YES | **MERGE** | `uaart_backup.yml` |
| 41 | `.github/workflows/task067_read_only_audit.yml` | push | `task067-crm-online-guard-read-only-audit` | YES | NO | YES | NO | YES | NO | **MERGE** | `uaart_critical.yml` |
| 42 | `.github/workflows/task068_catalog_structure_probe.yml` | workflow_dispatch, push | `NONE` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 43 | `.github/workflows/task068_ferry_vin_deploy.yml` | workflow_dispatch, push | `task068-ferry-vin-v1-1-deploy` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 44 | `.github/workflows/task068_ferry_vin_probe.yml` | workflow_dispatch, push | `task068-ferry-vin-probe` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 45 | `.github/workflows/task069_crm_container_gate_a.yml` | workflow_dispatch, push | `task069-crm-container-gate-a` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 46 | `.github/workflows/task069_crm_container_gate_b.yml` | workflow_dispatch, push | `task069-crm-container-production-gate-b` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 47 | `.github/workflows/task069_crm_container_readonly.yml` | workflow_dispatch, push | `task069-crm-container-readonly-audit` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 48 | `.github/workflows/task070_real_context_probe.yml` | workflow_dispatch, push | `task070-real-crm-context-read` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 49 | `.github/workflows/task071_call_path_read.yml` | workflow_dispatch, push | `task071-current-crm-call-path-read` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 50 | `.github/workflows/task072_gate_a_v2.yml` | workflow_dispatch, push | `task072-gate-a-v2` | YES | NO | YES | NO | YES | YES | **ARCHIVE** | `uaart_standard.yml` |
| 51 | `.github/workflows/task072_gate_b.yml` | workflow_dispatch | `task072-description-production-gate-b` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 52 | `.github/workflows/task073_gate_a_live_probe.yml` | workflow_dispatch, push | `task073-live-readonly-gate-a-probe` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 53 | `.github/workflows/task073_gate_a_v5.yml` | workflow_dispatch, push | `NONE` | YES | NO | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 54 | `.github/workflows/task073_gate_b_v5.yml` | workflow_dispatch | `ua-art-production-crm` | YES | NO | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 55 | `.github/workflows/task074_catalog_card_unify.yml` | workflow_dispatch, push | `ua-art-production-write` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 56 | `.github/workflows/task075_stage_guard_sandbox.yml` | workflow_dispatch, push, pull_request | `task075-sandbox-canary` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 57 | `.github/workflows/task076_eta_gate_a_live.yml` | workflow_dispatch, push | `task076-eta-gate-a-live` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 58 | `.github/workflows/task077_container_stage_sync_gate_a.yml` | workflow_dispatch, push | `task077-container-stage-sync-gate-a` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 59 | `.github/workflows/task077_container_stage_sync_gate_b.yml` | workflow_dispatch | `ua-art-production-writer` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 60 | `.github/workflows/task078_voice_watchdog_gate_a.yml` | workflow_dispatch, push | `task078-voice-watchdog-gate-a` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 61 | `.github/workflows/task080_price_candidate.yml` | workflow_dispatch, push | `task080-price-candidate` | YES | NO | YES | NO | NO | YES | **MERGE** | `uaart_critical.yml` |
| 62 | `.github/workflows/task080_price_gate_a.yml` | workflow_dispatch, push | `task080-price-recognition-gate-a` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 63 | `.github/workflows/task081_publish_repair_gate_a_v2.yml` | workflow_dispatch, push | `task081-publish-repair-gate-a-v3` | YES | NO | YES | NO | YES | YES | **ARCHIVE** | `uaart_standard.yml` |
| 64 | `.github/workflows/task081_publish_repair_gate_b_v2.yml` | workflow_dispatch | `ua-art-production-crm` | YES | NO | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 65 | `.github/workflows/task081_publish_repair_live_audit_v2.yml` | workflow_dispatch, push | `task081-publish-repair-live-audit-v2` | YES | NO | YES | NO | NO | YES | **ARCHIVE** | `uaart_standard.yml` |
| 66 | `.github/workflows/task082_audit_probe.yml` | workflow_dispatch, push | `task082-audit-probe` | YES | NO | YES | NO | NO | YES | **MERGE** | `uaart_critical.yml` |
| 67 | `.github/workflows/task082_audit_probe_persist.yml` | workflow_dispatch, push | `NONE` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 68 | `.github/workflows/task082_catalog_stage_production.yml` | workflow_dispatch | `NONE` | NO | NO | YES | NO | NO | YES | **MERGE** | `uaart_critical.yml` |
| 69 | `.github/workflows/task082_live_source_probe.yml` | workflow_dispatch, push | `task082-vin4-live-source-probe` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 70 | `.github/workflows/task082_source_probe_persist.yml` | workflow_dispatch, push | `NONE` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 71 | `.github/workflows/task082_stage_probe.yml` | workflow_dispatch, push | `task082-stage-probe` | YES | NO | NO | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 72 | `.github/workflows/task082_vin4_title_deploy.yml` | workflow_dispatch, push | `task082-vin4-title-production` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 73 | `.github/workflows/task082_vin4_title_production.yml` | workflow_dispatch, push | `ua-art-production-crm` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 74 | `.github/workflows/task083_catalog_dedup.yml` | workflow_dispatch, push | `task083-catalog-dedup-verification` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 75 | `.github/workflows/task083_production_hold.yml` | workflow_dispatch, push | `NONE` | NO | NO | YES | NO | NO | YES | **MERGE** | `uaart_critical.yml` |
| 76 | `.github/workflows/task083_publish_transaction.yml` | workflow_dispatch, push | `task083-publish-transaction-production` | YES | NO | YES | YES | YES | YES | **MERGE** | `uaart_backup.yml` |
| 77 | `.github/workflows/task084_crm_hang_remediation_gate_a.yml` | workflow_dispatch, push | `task084-crm-hang-remediation-gate-a` | YES | NO | YES | NO | NO | YES | **MERGE** | `uaart_rollback.yml` |
| 78 | `.github/workflows/task084_crm_hang_root_cause.yml` | workflow_dispatch, push | `task084-crm-hang-root-cause-live-audit` | YES | NO | NO | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 79 | `.github/workflows/task084_crm_hang_root_cause_production.yml` | workflow_dispatch, push | `task084-crm-hang-remediation` | YES | NO | YES | YES | YES | YES | **MERGE** | `uaart_critical.yml` |
| 80 | `.github/workflows/task084_gate_a_live_read_only.yml` | workflow_dispatch, push | `task084-ua0011-read-only-gate-a` | YES | NO | NO | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 81 | `.github/workflows/task084_korea_reset_gate_a.yml` | workflow_dispatch, push | `task084-ua0011-korea-reset-gate-a` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 82 | `.github/workflows/task085_stage_payload_reset_production.yml` | workflow_dispatch | `NONE` | YES | NO | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 83 | `.github/workflows/task086_public_catalog_readonly_probe.yml` | workflow_dispatch, push | `NONE` | NO | NO | YES | NO | NO | YES | **MERGE** | `uaart_critical.yml` |
| 84 | `.github/workflows/task086_renderer_gate_a.yml` | workflow_dispatch, push | `NONE` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 85 | `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml` | workflow_dispatch, push | `ua-art-production-writer` | YES | NO | YES | YES | YES | YES | **MERGE** | `uaart_backup.yml` |
| 86 | `.github/workflows/task087_ua0011_korea_stage_production.yml` | workflow_dispatch | `NONE` | YES | NO | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 87 | `.github/workflows/task089_crm_voice_photo_live_audit.yml` | workflow_dispatch, push | `task089-crm-voice-photo-live-audit` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 88 | `.github/workflows/task090_catalog_design_restore.yml` | workflow_dispatch, push | `ua-art-production-writer` | YES | NO | YES | YES | YES | YES | **MERGE** | `uaart_backup.yml` |
| 89 | `.github/workflows/task091_numeric_claim_guard.yml` | workflow_dispatch, push | `ua-art-production-writer` | YES | NO | YES | YES | YES | YES | **MERGE** | `uaart_backup.yml` |
| 90 | `.github/workflows/task092_anthropic_reset_autostart.yml` | workflow_dispatch, schedule | `task092-claude-autostart` | NO | YES | NO | NO | YES | YES | **ARCHIVE** | `uaart_fast.yml` |
| 91 | `.github/workflows/task092_autostart.yml` | workflow_dispatch | `NONE` | NO | YES | NO | NO | YES | YES | **ARCHIVE** | `uaart_fast.yml` |
| 92 | `.github/workflows/task092_launch_after_limit.yml` | workflow_dispatch, push | `task092-claude-autopilot` | NO | YES | NO | NO | YES | YES | **ARCHIVE** | `uaart_fast.yml` |
| 93 | `.github/workflows/task093_home_stage_counter_sync_production.yml` | workflow_dispatch, push | `ua-art-production-writer` | YES | NO | YES | YES | YES | YES | **MERGE** | `uaart_backup.yml` |
| 94 | `.github/workflows/task094_claude_autostart.yml` | workflow_dispatch, push | `claude-autopilot` | NO | YES | YES | NO | YES | YES | **ARCHIVE** | `uaart_rollback.yml` |
| 95 | `.github/workflows/task095_catalog_visual_diagnostic.yml` | workflow_dispatch, push | `ua-art-task095-visual-diagnostic` | NO | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 96 | `.github/workflows/task095_catalog_visual_repair.yml` | workflow_dispatch, push | `ua-art-production-writer` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 97 | `.github/workflows/task095_catalog_visual_repair_v2.yml` | workflow_dispatch, push | `ua-art-production-writer` | YES | NO | YES | NO | YES | YES | **ARCHIVE** | `uaart_backup.yml` |
| 98 | `.github/workflows/task095_catalog_visual_repair_v3.yml` | workflow_dispatch, push | `ua-art-production-writer` | YES | NO | YES | NO | NO | YES | **ARCHIVE** | `uaart_backup.yml` |
| 99 | `.github/workflows/task096_autorun_orchestrator.yml` | workflow_dispatch, push | `task096-autorun-orchestrator` | YES | YES | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 100 | `.github/workflows/task096_claude_sandbox.yml` | workflow_dispatch, push | `task096-claude-sandbox` | NO | YES | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 101 | `.github/workflows/task096_controller_sandbox.yml` | workflow_dispatch, push | `task096-controller-sandbox` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 102 | `.github/workflows/task096_data_enrichment_sandbox.yml` | workflow_dispatch, push | `task096-data-enrichment-sandbox` | YES | YES | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 103 | `.github/workflows/task096_enrichment_repair_v2.yml` | workflow_dispatch, push | `task096-autorun` | YES | YES | YES | NO | YES | YES | **ARCHIVE** | `uaart_critical.yml` |
| 104 | `.github/workflows/task096_enrichment_repair_v3.yml` | workflow_dispatch, push | `task096-autorun` | YES | YES | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 105 | `.github/workflows/task096_enrichment_repair_v4.yml` | workflow_dispatch, push | `task096-autorun` | YES | YES | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 106 | `.github/workflows/task096_enrichment_repair_v5.yml` | workflow_dispatch, push | `task096-autorun` | YES | YES | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 107 | `.github/workflows/task096_enrichment_repair_v6.yml` | workflow_dispatch, push | `task096-autorun` | YES | YES | YES | NO | NO | YES | **ARCHIVE** | `uaart_critical.yml` |
| 108 | `.github/workflows/task096_enrichment_repair_v7.yml` | workflow_dispatch, push | `task096-autorun` | YES | YES | YES | NO | YES | YES | **ARCHIVE** | `uaart_critical.yml` |
| 109 | `.github/workflows/task096_enrichment_repair_v8.yml` | workflow_dispatch, push | `task096-autorun` | YES | YES | YES | NO | YES | YES | **ARCHIVE** | `uaart_critical.yml` |
| 110 | `.github/workflows/task096_final_fix.yml` | workflow_dispatch, push | `NONE` | YES | YES | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 111 | `.github/workflows/task096_recovery10.yml` | workflow_dispatch, push | `task096-data-enrichment-sandbox` | YES | YES | YES | NO | YES | YES | **ARCHIVE** | `uaart_critical.yml` |
| 112 | `.github/workflows/task096_repair_trigger.yml` | workflow_dispatch, push | `NONE` | NO | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 113 | `.github/workflows/task097_editorial_atlas_audit.yml` | workflow_dispatch, push | `task097-editorial-atlas-audit` | YES | YES | YES | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 114 | `.github/workflows/task098_editorial_atlas_qa.yml` | workflow_dispatch, push | `task098-editorial-atlas-qa` | NO | YES | YES | NO | YES | YES | **MERGE** | `uaart_standard.yml` |
| 115 | `.github/workflows/task098_editorial_atlas_qa_retry.yml` | workflow_dispatch, push | `task098-editorial-atlas-qa` | NO | YES | YES | NO | YES | YES | **ARCHIVE** | `uaart_standard.yml` |
| 116 | `.github/workflows/task099_live_audit.yml` | workflow_dispatch, push | `task099-site-crm-completion` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_rollback.yml` |
| 117 | `.github/workflows/task099_partial_recovery.yml` | workflow_dispatch, push | `task099-site-crm-production` | YES | NO | YES | NO | YES | YES | **ARCHIVE** | `uaart_rollback.yml` |
| 118 | `.github/workflows/task099_remote_state_probe.yml` | workflow_dispatch, push | `NONE` | YES | NO | YES | NO | NO | YES | **MERGE** | `uaart_critical.yml` |
| 119 | `.github/workflows/task099_site_crm_production.yml` | workflow_dispatch, push | `task099-site-crm-production` | YES | NO | YES | NO | YES | YES | **MERGE** | `uaart_backup.yml` |
| 120 | `.github/workflows/task100_home_live_sync.yml` | workflow_dispatch, push | `ua-art-production-writer` | YES | NO | YES | YES | NO | YES | **MERGE** | `uaart_backup.yml` |
| 121 | `.github/workflows/task102_seo_audit.yml` | workflow_dispatch, push | `task102-seo-readonly-audit` | YES | NO | YES | NO | NO | YES | **MERGE** | `uaart_standard.yml` |
| 122 | `.github/workflows/task102_seo_routing_probe.yml` | workflow_dispatch, push | `NONE` | YES | NO | NO | NO | NO | YES | **MERGE** | `uaart_monitor.yml` |
| 123 | `.github/workflows/task103_ge_8country_sandbox_autostart.yml` | workflow_dispatch, push | `claude-autopilot` | NO | YES | YES | NO | YES | YES | **ARCHIVE** | `uaart_critical.yml` |
| 124 | `.github/workflows/task104_canary_recovery.yml` | workflow_run | `task104-canary-recovery` | NO | NO | NO | NO | YES | NO | **ARCHIVE** | `uaart_fast.yml` |
| 125 | `.github/workflows/task104_canary_worker.yml` | workflow_dispatch | `task104-canary-${{ inputs.cycle }}` | NO | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 126 | `.github/workflows/task104_integration_canary.yml` | workflow_dispatch, push | `task104-integration-canary` | NO | NO | YES | NO | YES | YES | **MERGE** | `uaart_critical.yml` |
| 127 | `.github/workflows/task104_self_recovery_sandbox.yml` | workflow_dispatch, push | `task104-self-recovery-sandbox` | NO | NO | YES | NO | YES | YES | **ARCHIVE** | `uaart_critical.yml` |
| 128 | `.github/workflows/task105_phase0_audit.yml` | workflow_dispatch, push | `task105-phase0-audit` | YES | NO | YES | NO | NO | YES | **MERGE** | `uaart_critical.yml` |
| 129 | `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml` | workflow_dispatch, push | `ua-art-autopilot-core-v2-sandbox` | YES | NO | YES | NO | YES | YES | **ARCHIVE** | `uaart_rollback.yml` |

## Per-workflow rationale

### `.github/workflows/claude_autopilot.yml`
- Decision: **KEEP** → `uaart_critical.yml`
- Rationale: Базовый действующий контур; сохранить до доказанного функционального эквивалента.
- Referenced workflows: NONE
- Referenced scripts: `automation/claude_worker.py`

### `.github/workflows/ferry_wording_gate_a.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Функцию следует объединить с постоянным параметризованным pipeline.
- Referenced workflows: `.github/workflows/ferry_wording_gate_a.yml`
- Referenced scripts: `cloud/task_047_ferry_discovery/discover.py`, `cloud/task_047_ferry_discovery/evidence/ferry_gate_a.js`, `cloud/task_047_ferry_discovery/gate_a_controller.py`, `cloud/task_047_ferry_discovery/gate_a_remote.py`, `cloud/task_047_ferry_discovery/run_tests.py`, `cloud/task_047_ferry_discovery/transform.py`

### `.github/workflows/ferry_wording_gate_b.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Функцию следует объединить с постоянным параметризованным pipeline.
- Referenced workflows: `.github/workflows/ferry_wording_gate_b.yml`
- Referenced scripts: `cloud/task_047_ferry_discovery/evidence/ferry_gate_b.js`, `cloud/task_047_ferry_discovery/evidence/ferry_gate_b_live.js`, `cloud/task_047_ferry_discovery/gate_b_controller.py`, `cloud/task_047_ferry_discovery/gate_b_live_verify.py`, `cloud/task_047_ferry_discovery/gate_b_remote.py`, `cloud/task_047_ferry_discovery/gate_b_tests.py`, `cloud/task_047_ferry_discovery/run_tests.py`

### `.github/workflows/overnight_autopilot_production_dispatch.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Функцию следует объединить с постоянным параметризованным pipeline.
- Referenced workflows: NONE
- Referenced scripts: `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`

### `.github/workflows/overnight_task099_transient_recovery.yml`
- Decision: **ARCHIVE** → `uaart_rollback.yml`
- Rationale: Версионный инфраструктурный вариант; проверить преемника и затем архивировать.
- Referenced workflows: NONE
- Referenced scripts: NONE

### `.github/workflows/owner_ua0011_full_card_gate_a.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Функцию следует объединить с постоянным параметризованным pipeline.
- Referenced workflows: `.github/workflows/owner_ua0011_full_card_gate_a.yml`
- Referenced scripts: `cloud/task_088_ua0011_korea/evidence/full_card_gate_a.js`

### `.github/workflows/owner_ua0011_korea_now_production.yml`
- Decision: **ARCHIVE** → `uaart_backup.yml`
- Rationale: Версионный инфраструктурный вариант; проверить преемника и затем архивировать.
- Referenced workflows: `.github/workflows/owner_ua0011_korea_now_production.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_085_stage_payload_reset/controller.py`, `cloud/task_085_stage_payload_reset/evidence/production.js`, `cloud/task_085_stage_payload_reset/remote_installer.py`, `cloud/task_085_stage_payload_reset/stage_payload_guard.py`, `cloud/task_085_stage_payload_reset/tests/test_remote_installer.py`, `cloud/task_085_stage_payload_reset/tests/test_stage_payload_guard.py`

### `.github/workflows/owner_ua0011_korea_slim_production.yml`
- Decision: **ARCHIVE** → `uaart_backup.yml`
- Rationale: Версионный инфраструктурный вариант; проверить преемника и затем архивировать.
- Referenced workflows: `.github/workflows/owner_ua0011_korea_slim_production.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_085_stage_payload_reset/controller.py`, `cloud/task_085_stage_payload_reset/evidence/production.js`, `cloud/task_085_stage_payload_reset/remote_installer.py`, `cloud/task_085_stage_payload_reset/stage_payload_guard.py`, `cloud/task_085_stage_payload_reset/tests/test_remote_installer.py`, `cloud/task_085_stage_payload_reset/tests/test_stage_payload_guard.py`

### `.github/workflows/pythonanywhere_sync.yml`
- Decision: **KEEP** → `uaart_critical.yml`
- Rationale: Базовый действующий контур; сохранить до доказанного функционального эквивалента.
- Referenced workflows: `.github/workflows/pythonanywhere_sync.yml`
- Referenced scripts: `automation/pythonanywhere_sync_v2.py`

### `.github/workflows/safe_workflow_watchdog.yml`
- Decision: **KEEP** → `uaart_critical.yml`
- Rationale: Базовый действующий контур; сохранить до доказанного функционального эквивалента.
- Referenced workflows: `.github/workflows/safe_workflow_watchdog.yml`
- Referenced scripts: NONE

### `.github/workflows/seo-rehab-068-production.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Функцию следует объединить с постоянным параметризованным pipeline.
- Referenced workflows: `.github/workflows/seo-rehab-068-production.yml`
- Referenced scripts: `cloud/seo_rehab_guard_068/controller.py`, `cloud/seo_rehab_guard_068/evidence/controller.js`, `cloud/seo_rehab_guard_068/live_verify.py`, `cloud/seo_rehab_guard_068/repair_remote.py`

### `.github/workflows/seo-watch-smoke.yml`
- Decision: **KEEP** → `uaart_monitor.yml`
- Rationale: Базовый действующий контур; сохранить до доказанного функционального эквивалента.
- Referenced workflows: `.github/workflows/seo-watch-smoke.yml`
- Referenced scripts: NONE

### `.github/workflows/task037_discovery.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task037_discovery.yml`
- Referenced scripts: `cloud/bot_logistics/evidence/task_037_discovery.js`, `cloud/bot_logistics/pythonanywhere_discovery_controller.py`

### `.github/workflows/task039_retry.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task039_retry.yml`
- Referenced scripts: `cloud/bot_logistics/bot_logistics_discovery.py`, `cloud/bot_logistics/pythonanywhere_discovery_controller.py`, `cloud/bot_logistics/test_bot_logistics.py`, `cloud/bot_logistics/test_discovery_controller.py`

### `.github/workflows/task039_safe_inbox_sync.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task039_safe_inbox_sync.yml`
- Referenced scripts: `automation/pythonanywhere_sync_v2.py`

### `.github/workflows/task049_gate_a.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task049_gate_a.yml`
- Referenced scripts: `cloud/bot_logistics/evidence/task_049_gate_a.js`, `cloud/bot_logistics/task049_gate_a_controller.py`

### `.github/workflows/task049_gate_b.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task049_gate_b.yml`
- Referenced scripts: `cloud/bot_logistics/evidence/task_049_gate_b.js`, `cloud/bot_logistics/task049_gate_b_controller.py`

### `.github/workflows/task049_gate_b_preflight.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task049_gate_b_preflight.yml`
- Referenced scripts: `cloud/bot_logistics/evidence/task_049_gate_b_preflight.js`, `cloud/bot_logistics/task049_gate_b_preflight.py`

### `.github/workflows/task058_crm_ocr_readonly.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: NONE
- Referenced scripts: `cloud/task_058_crm_ocr_sync/evidence/task_058_live_discovery.js`, `cloud/task_058_crm_ocr_sync/run_tests.py`, `cloud/task_058_crm_ocr_sync/task058_readonly_controller.py`

### `.github/workflows/task059_ai_fast_schema.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: NONE
- Referenced scripts: `cloud/task_059_ai_fast_schema/ai_fast_schema.py`, `cloud/task_059_ai_fast_schema/evidence/task_059_install.js`, `cloud/task_059_ai_fast_schema/patch_installer.py`, `cloud/task_059_ai_fast_schema/patch_payload.py`, `cloud/task_059_ai_fast_schema/task059_controller.py`

### `.github/workflows/task060_install_token_free_ocr.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task060_install_token_free_ocr.yml`
- Referenced scripts: `cloud/task_060/evidence/install.js`, `cloud/task_060/install_controller.py`, `cloud/task_060/local_ocr.py`, `cloud/task_060/patch_installer.py`, `cloud/task_060/patch_payload.py`

### `.github/workflows/task060_read_live_context.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task060_read_live_context.yml`
- Referenced scripts: `cloud/task_060/evidence/live_context.js`, `cloud/task_060/read_live_context.py`

### `.github/workflows/task060_runtime_capabilities.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task060_runtime_capabilities.yml`
- Referenced scripts: `cloud/task_060/evidence/runtime_capabilities.js`, `cloud/task_060/probe_runtime.py`

### `.github/workflows/task061_crm_ai_card.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task061_crm_ai_card.yml`
- Referenced scripts: `cloud/task_061/evidence/install.js`, `cloud/task_061/install_controller.py`, `cloud/task_061/local_ocr.py`, `cloud/task_061/patch_installer.py`, `cloud/task_061/patch_payload.py`, `cloud/task_061/test_contract.py`

### `.github/workflows/task062_crm_voice.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task062_crm_voice.yml`
- Referenced scripts: `cloud/task_061/local_ocr.py`, `cloud/task_062/evidence/install.js`, `cloud/task_062/install_controller.py`, `cloud/task_062/patch_installer.py`, `cloud/task_062/patch_payload.py`, `cloud/task_062/postcheck.py`, `cloud/task_062/test_contract.py`

### `.github/workflows/task062_read_voice_context.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task062_read_voice_context.yml`
- Referenced scripts: `cloud/task_062/evidence/voice_context.js`, `cloud/task_062/read_voice_context.py`

### `.github/workflows/task064_crm_db_lock_hotfix.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task064_crm_db_lock_hotfix.yml`
- Referenced scripts: `cloud/task_064/evidence/hotfix.js`, `cloud/task_064/hotfix_controller.py`, `cloud/task_064/sqlite_hotfix_installer.py`, `cloud/task_064/sqlite_hotfix_postcheck.py`, `cloud/task_064/test_sqlite_hotfix.py`

### `.github/workflows/task064_diagnostics_permanent.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task064_diagnostics_permanent.yml`
- Referenced scripts: `cloud/task_064_diagnostics/controller.py`, `cloud/task_064_diagnostics/evidence/live.js`, `cloud/task_064_diagnostics/evidence/repair.js`, `cloud/task_064_diagnostics/live_verify.py`, `cloud/task_064_diagnostics/repair_remote.py`

### `.github/workflows/task064_emergency_crm_quiesce.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task064_emergency_crm_quiesce.yml`
- Referenced scripts: `cloud/task_064/emergency_quiesce.py`, `cloud/task_064/evidence/quiesce.js`

### `.github/workflows/task064_read_crm_lock_context.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task064_read_crm_lock_context.yml`
- Referenced scripts: `cloud/task_064/evidence/lock_context.js`, `cloud/task_064/read_lock_context.py`

### `.github/workflows/task064_trace_wrapper_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task064_trace_wrapper_probe.yml`
- Referenced scripts: `cloud/task_064/evidence/trace_wrapper.js`, `cloud/task_064/read_trace_wrapper.py`

### `.github/workflows/task065_counter_v2_hotfix.yml`
- Decision: **ARCHIVE** → `uaart_standard.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task065_counter_v2_hotfix.yml`
- Referenced scripts: `cloud/task_065/counter_v2_controller.py`, `cloud/task_065/counter_v2_installer.py`, `cloud/task_065/counter_v2_postcheck.py`, `cloud/task_065/evidence/counter_v2_hotfix.js`, `cloud/task_065/voice_fields_repair.py`

### `.github/workflows/task065_crm_photo_fastpath.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task065_crm_photo_fastpath.yml`
- Referenced scripts: `cloud/task_065/evidence/hotfix.js`, `cloud/task_065/hotfix_controller.py`, `cloud/task_065/photo_fastpath_installer.py`, `cloud/task_065/photo_fastpath_postcheck.py`

### `.github/workflows/task065_photo_path_probe.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task065_photo_path_probe.yml`
- Referenced scripts: `cloud/task_065/evidence/photo_path.js`, `cloud/task_065/read_photo_path.py`

### `.github/workflows/task065_ua0011_probe.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task065_ua0011_probe.yml`
- Referenced scripts: `cloud/task_065/evidence/ua0011_counts.js`, `cloud/task_065/read_ua0011_counts.py`

### `.github/workflows/task065_voice_path_probe.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task065_voice_path_probe.yml`
- Referenced scripts: `cloud/task_065/evidence/voice_path.js`, `cloud/task_065/read_voice_path.py`

### `.github/workflows/task066_stage_anchor_deploy.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task066_stage_anchor_deploy.yml`
- Referenced scripts: `cloud/task_066_stage_anchor/controller.py`, `cloud/task_066_stage_anchor/evidence/deploy.js`, `cloud/task_066_stage_anchor/evidence/live.js`, `cloud/task_066_stage_anchor/live_verify.py`, `cloud/task_066_stage_anchor/postcheck_remote.py`, `cloud/task_066_stage_anchor/repair_remote.py`

### `.github/workflows/task066_stage_anchor_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task066_stage_anchor_probe.yml`
- Referenced scripts: `cloud/task_066_stage_anchor/evidence/current.js`, `cloud/task_066_stage_anchor/read_current.py`

### `.github/workflows/task067_crm_online_guard_deploy.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task067_crm_online_guard_deploy.yml`
- Referenced scripts: `cloud/task_067/controller.py`, `cloud/task_067/crm_online_guard.py`, `cloud/task_067/evidence/deploy.js`, `cloud/task_067/installer.py`, `cloud/task_067/postcheck.py`, `cloud/task_067/soak.py`

### `.github/workflows/task067_health_probe.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task067_health_probe.yml`
- Referenced scripts: NONE

### `.github/workflows/task067_read_only_audit.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task067_read_only_audit.yml`
- Referenced scripts: `cloud/task_067/audit.py`, `cloud/task_067/evidence/read_only_audit.js`

### `.github/workflows/task068_catalog_structure_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task068_catalog_structure_probe.yml`
- Referenced scripts: `cloud/task_068_ferry_vin/evidence/catalog_structure_probe.js`

### `.github/workflows/task068_ferry_vin_deploy.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task068_ferry_vin_deploy.yml`
- Referenced scripts: `cloud/task_068_ferry_vin/controller.py`, `cloud/task_068_ferry_vin/evidence/deploy.js`, `cloud/task_068_ferry_vin/evidence/live.js`, `cloud/task_068_ferry_vin/live_verify.py`, `cloud/task_068_ferry_vin/postcheck_remote.py`, `cloud/task_068_ferry_vin/repair_remote.py`, `cloud/task_068_ferry_vin/source_shadow.py`

### `.github/workflows/task068_ferry_vin_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task068_ferry_vin_probe.yml`
- Referenced scripts: `cloud/task_068_ferry_vin/evidence/current.js`, `cloud/task_068_ferry_vin/read_current.py`

### `.github/workflows/task069_crm_container_gate_a.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task069_crm_container_gate_a.yml`
- Referenced scripts: `cloud/task_069/evidence/gate_a.js`, `cloud/task_069/gate_a.py`

### `.github/workflows/task069_crm_container_gate_b.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task069_crm_container_gate_b.yml`
- Referenced scripts: `cloud/task_069/evidence/gate_b.js`, `cloud/task_069/gate_b_controller.py`, `cloud/task_069/gate_b_installer.py`, `cloud/task_069/gate_b_postcheck.py`

### `.github/workflows/task069_crm_container_readonly.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task069_crm_container_readonly.yml`
- Referenced scripts: `cloud/task_069/evidence/current.js`, `cloud/task_069/read_current.py`

### `.github/workflows/task070_real_context_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task070_real_context_probe.yml`
- Referenced scripts: `cloud/task_070/evidence/real_context.js`, `cloud/task_070/read_real_context.py`

### `.github/workflows/task071_call_path_read.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task071_call_path_read.yml`
- Referenced scripts: `cloud/task_071/evidence/call_path.js`, `cloud/task_071/read_call_path.py`

### `.github/workflows/task072_gate_a_v2.yml`
- Decision: **ARCHIVE** → `uaart_standard.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task072_gate_a_v2.yml`, `.github/workflows/task072_gate_b.yml`
- Referenced scripts: `cloud/task_072/crm_description_writer_v2.py`, `cloud/task_072/evidence/gate_a_v2.js`, `cloud/task_072/gate_a_v2.py`, `cloud/task_072/gate_b_controller_v2.py`, `cloud/task_072/installer_v2.py`, `cloud/task_072/patch_cars_ui_v2.py`, `cloud/task_072/postcheck_v2.py`

### `.github/workflows/task072_gate_b.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: NONE
- Referenced scripts: `cloud/task_072/crm_description_writer_v2.py`, `cloud/task_072/evidence/gate_a_v2.js`, `cloud/task_072/evidence/gate_b_v2.js`, `cloud/task_072/gate_b_controller_v2.py`, `cloud/task_072/installer_v2.py`, `cloud/task_072/patch_cars_ui_v2.py`, `cloud/task_072/postcheck_v2.py`

### `.github/workflows/task073_gate_a_live_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task073_gate_a_live_probe.yml`
- Referenced scripts: `cloud/task_073/evidence/live_probe.js`, `cloud/task_073/gate_a_live_probe.py`

### `.github/workflows/task073_gate_a_v5.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task073_gate_a_v5.yml`
- Referenced scripts: `cloud/task_073/evidence/gate_a_v5.js`

### `.github/workflows/task073_gate_b_v5.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: NONE
- Referenced scripts: `cloud/task_073/evidence/gate_a_v5.js`, `cloud/task_073/evidence/gate_b_v5.js`

### `.github/workflows/task074_catalog_card_unify.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task074_catalog_card_unify.yml`
- Referenced scripts: `cloud/task_074_catalog_unify/controller.py`, `cloud/task_074_catalog_unify/evidence/controller.js`, `cloud/task_074_catalog_unify/installer.py`, `cloud/task_074_catalog_unify/tests/test_installer.py`

### `.github/workflows/task075_stage_guard_sandbox.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task075_stage_guard_sandbox.yml`
- Referenced scripts: `cloud/task_075_stage_guard/evidence/sandbox.js`, `cloud/task_075_stage_guard/live_sandbox.py`, `cloud/task_075_stage_guard/stage_guard.py`, `cloud/task_075_stage_guard/tests/test_stage_guard.py`

### `.github/workflows/task076_eta_gate_a_live.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task076_eta_gate_a_live.yml`
- Referenced scripts: `cloud/task_076_eta_sync/evidence/gate_a_live.js`, `cloud/task_076_eta_sync/gate_a_live.py`, `cloud/task_076_eta_sync/run_tests.py`

### `.github/workflows/task077_container_stage_sync_gate_a.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task077_container_stage_sync_gate_a.yml`
- Referenced scripts: `cloud/task_076_eta_sync/eta_engine.py`, `cloud/task_077_container_stage_sync/evidence/live_audit.js`, `cloud/task_077_container_stage_sync/gate_b/controller.py`, `cloud/task_077_container_stage_sync/gate_b/remote.py`, `cloud/task_077_container_stage_sync/live_audit.py`, `cloud/task_077_container_stage_sync/patcher/eta_release_candidate.py`, `cloud/task_077_container_stage_sync/patcher/live_patcher.py`, `cloud/task_077_container_stage_sync/stage_sync.py`, `cloud/task_077_container_stage_sync/tests/test_eta_release_candidate.py`, `cloud/task_077_container_stage_sync/tests/test_gate_b_release.py`, `cloud/task_077_container_stage_sync/tests/test_stage_sync.py`

### `.github/workflows/task077_container_stage_sync_gate_b.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: NONE
- Referenced scripts: `cloud/task_076_eta_sync/eta_engine.py`, `cloud/task_077_container_stage_sync/evidence/gate_b.js`, `cloud/task_077_container_stage_sync/gate_b/controller.py`, `cloud/task_077_container_stage_sync/gate_b/remote.py`, `cloud/task_077_container_stage_sync/patcher/eta_release_candidate.py`, `cloud/task_077_container_stage_sync/patcher/live_patcher.py`, `cloud/task_077_container_stage_sync/tests/test_eta_release_candidate.py`, `cloud/task_077_container_stage_sync/tests/test_gate_b_release.py`

### `.github/workflows/task078_voice_watchdog_gate_a.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task078_voice_watchdog_gate_a.yml`
- Referenced scripts: `cloud/task_078_voice_watchdog/evidence/live_audit.js`, `cloud/task_078_voice_watchdog/handler_patcher.py`, `cloud/task_078_voice_watchdog/live_audit.py`, `cloud/task_078_voice_watchdog/tests/test_handler_patcher.py`, `cloud/task_078_voice_watchdog/tests/test_voice_watchdog.py`, `cloud/task_078_voice_watchdog/tests/test_watchdog.py`, `cloud/task_078_voice_watchdog/voice_watchdog.py`

### `.github/workflows/task080_price_candidate.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task080_price_candidate.yml`
- Referenced scripts: `cloud/task_080_price_recognition/candidate_gate_a.py`, `cloud/task_080_price_recognition/evidence/candidate_gate_a.js`, `cloud/task_080_price_recognition/evidence/test_run.js`, `cloud/task_080_price_recognition/run_tests.py`, `cloud/task_080_price_recognition/src/crm_price_atomic.py`, `cloud/task_080_price_recognition/src/integration_patcher.py`, `cloud/task_080_price_recognition/src/price_parser.py`, `cloud/task_080_price_recognition/tests/test_crm_price_atomic.py`, `cloud/task_080_price_recognition/tests/test_integration_patcher.py`, `cloud/task_080_price_recognition/tests/test_price_parser.py`

### `.github/workflows/task080_price_gate_a.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task080_price_gate_a.yml`
- Referenced scripts: `cloud/task_080_price_recognition/evidence/live_gate_a.js`, `cloud/task_080_price_recognition/live_gate_a.py`, `cloud/task_080_price_recognition/src/patcher.py`, `cloud/task_080_price_recognition/src/price_parser.py`, `cloud/task_080_price_recognition/tests/test_price_parser.py`

### `.github/workflows/task081_publish_repair_gate_a_v2.yml`
- Decision: **ARCHIVE** → `uaart_standard.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task081_publish_repair_gate_a_v2.yml`
- Referenced scripts: `cloud/task_081_publish_repair/controller.py`, `cloud/task_081_publish_repair/evidence/live_audit_v2.js`, `cloud/task_081_publish_repair/installer.py`, `cloud/task_081_publish_repair/live_probe_v2.py`, `cloud/task_081_publish_repair/patcher.py`, `cloud/task_081_publish_repair/postcheck.py`

### `.github/workflows/task081_publish_repair_gate_b_v2.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: NONE
- Referenced scripts: `cloud/task_081_publish_repair/evidence/gate_a_v2.js`, `cloud/task_081_publish_repair/evidence/gate_b_v2.js`, `cloud/task_081_publish_repair/evidence/live_audit_v2/live_audit.js`, `cloud/task_081_publish_repair/gate_a_v2.py`, `cloud/task_081_publish_repair/live_audit_v2.py`, `cloud/task_081_publish_repair/test_gate_b_v2.py`, `cloud/task_081_publish_repair/test_release_candidate_v2.py`

### `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- Decision: **ARCHIVE** → `uaart_standard.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- Referenced scripts: `cloud/task_081_publish_repair/evidence/gate_a_v2.js`, `cloud/task_081_publish_repair/evidence/live_audit_v2/live_audit.js`, `cloud/task_081_publish_repair/gate_a_v2.py`, `cloud/task_081_publish_repair/gate_b_controller_v2.py`, `cloud/task_081_publish_repair/gate_b_installer_v2.py`, `cloud/task_081_publish_repair/live_audit_v2.py`, `cloud/task_081_publish_repair/patcher_v2.py`, `cloud/task_081_publish_repair/postcheck_v2.py`, `cloud/task_081_publish_repair/test_gate_b_v2.py`, `cloud/task_081_publish_repair/test_release_candidate_v2.py`

### `.github/workflows/task082_audit_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task082_audit_probe.yml`
- Referenced scripts: NONE

### `.github/workflows/task082_audit_probe_persist.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task082_audit_probe_persist.yml`
- Referenced scripts: `cloud/task_082_catalog_stage_repair/evidence/audit_probe.js`

### `.github/workflows/task082_catalog_stage_production.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: NONE
- Referenced scripts: NONE

### `.github/workflows/task082_live_source_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task082_live_source_probe.yml`
- Referenced scripts: `cloud/task_082_live_source_probe.py`, `cloud/task_082_probe/evidence.js`

### `.github/workflows/task082_source_probe_persist.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task082_source_probe_persist.yml`
- Referenced scripts: `cloud/task_082_catalog_stage_repair/evidence/source_probe.js`

### `.github/workflows/task082_stage_probe.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task082_stage_probe.yml`
- Referenced scripts: `cloud/task_082_catalog_stage_repair/evidence/stage_probe.js`, `cloud/task_082_catalog_stage_repair/stage_probe.py`

### `.github/workflows/task082_vin4_title_deploy.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task082_vin4_title_deploy.yml`
- Referenced scripts: `cloud/task_082_vin4_title/controller.py`, `cloud/task_082_vin4_title/evidence/deploy.js`, `cloud/task_082_vin4_title/repair_remote.py`

### `.github/workflows/task082_vin4_title_production.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task082_vin4_title_production.yml`
- Referenced scripts: `cloud/task_082_vin4_title/evidence/deploy_v2.js`

### `.github/workflows/task083_catalog_dedup.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task083_catalog_dedup.yml`
- Referenced scripts: `cloud/task_075_stage_guard/stage_guard.py`, `cloud/task_083_catalog_dedup/controller.py`, `cloud/task_083_catalog_dedup/evidence/controller.js`, `cloud/task_083_catalog_dedup/installer.py`, `cloud/task_083_catalog_dedup/tests/test_installer.py`

### `.github/workflows/task083_production_hold.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task083_production_hold.yml`
- Referenced scripts: NONE

### `.github/workflows/task083_publish_transaction.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task083_publish_transaction.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_075_stage_guard/stage_guard.py`, `cloud/task_083_publish_transaction/controller.py`, `cloud/task_083_publish_transaction/evidence/deploy.js`, `cloud/task_083_publish_transaction/public_verify.py`, `cloud/task_083_publish_transaction/publish_transaction_guard.py`, `cloud/task_083_publish_transaction/remote_installer.py`, `cloud/task_083_publish_transaction/tests/test_contract.py`

### `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
- Decision: **MERGE** → `uaart_rollback.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
- Referenced scripts: `cloud/task_078_voice_watchdog/handler_patcher.py`, `cloud/task_078_voice_watchdog/tests/test_handler_patcher.py`, `cloud/task_078_voice_watchdog/tests/test_voice_watchdog.py`, `cloud/task_078_voice_watchdog/voice_watchdog.py`, `cloud/task_084_crm_hang_root_cause/deploy_controller.py`, `cloud/task_084_crm_hang_root_cause/evidence/deploy.js`, `cloud/task_084_crm_hang_root_cause/evidence/live_audit.js`, `cloud/task_084_crm_hang_root_cause/live_audit.py`, `cloud/task_084_crm_hang_root_cause/remote_installer.py`, `cloud/task_084_crm_hang_root_cause/remote_orchestrator.py`, `cloud/task_084_crm_hang_root_cause/single_task_controller.py`

### `.github/workflows/task084_crm_hang_root_cause.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task084_crm_hang_root_cause.yml`
- Referenced scripts: `cloud/task_084_crm_hang_root_cause/evidence/live_audit.js`, `cloud/task_084_crm_hang_root_cause/live_audit.py`

### `.github/workflows/task084_crm_hang_root_cause_production.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task084_crm_hang_root_cause_production.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_078_voice_watchdog/handler_patcher.py`, `cloud/task_078_voice_watchdog/tests/test_handler_patcher.py`, `cloud/task_078_voice_watchdog/tests/test_voice_watchdog.py`, `cloud/task_078_voice_watchdog/voice_watchdog.py`, `cloud/task_084_crm_hang_root_cause/deploy_controller.py`, `cloud/task_084_crm_hang_root_cause/evidence/deploy.js`, `cloud/task_084_crm_hang_root_cause/evidence/live_audit.js`, `cloud/task_084_crm_hang_root_cause/live_audit.py`, `cloud/task_084_crm_hang_root_cause/remote_installer.py`

### `.github/workflows/task084_gate_a_live_read_only.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task084_gate_a_live_read_only.yml`
- Referenced scripts: `cloud/task_084_ua0011_korea_reset/evidence/live_gate_a_inventory.js`, `cloud/task_084_ua0011_korea_reset/live_gate_a_probe.py`

### `.github/workflows/task084_korea_reset_gate_a.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task084_korea_reset_gate_a.yml`
- Referenced scripts: `cloud/task_075_stage_guard/stage_guard.py`, `cloud/task_084_ua0011_korea_reset/evidence/live_gate_a.js`, `cloud/task_084_ua0011_korea_reset/fixtures/ua_cards_fixture.js`, `cloud/task_084_ua0011_korea_reset/guards.py`, `cloud/task_084_ua0011_korea_reset/live_gate_a.py`, `cloud/task_084_ua0011_korea_reset/renderer_fix.py`, `cloud/task_084_ua0011_korea_reset/sandbox_transform.py`, `cloud/task_084_ua0011_korea_reset/tests/test_gate_a_sandbox.py`

### `.github/workflows/task085_stage_payload_reset_production.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Короткий task-specific launcher/stub; после миграции сохранить только как историю.
- Referenced workflows: NONE
- Referenced scripts: NONE

### `.github/workflows/task086_public_catalog_readonly_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task086_public_catalog_readonly_probe.yml`
- Referenced scripts: NONE

### `.github/workflows/task086_renderer_gate_a.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task086_renderer_gate_a.yml`
- Referenced scripts: `cloud/task_086_ua0011_korea_stage/evidence/active_renderers.js`, `cloud/task_088_ua0011_korea/evidence/full_card_gate_a.js`

### `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_086_ua0011_ferry_stage_counter/controller.py`, `cloud/task_086_ua0011_ferry_stage_counter/evidence/production.js`, `cloud/task_086_ua0011_ferry_stage_counter/remote_installer.py`, `cloud/task_086_ua0011_ferry_stage_counter/stage_counter_guard.py`, `cloud/task_086_ua0011_ferry_stage_counter/tests/test_remote_installer.py`, `cloud/task_086_ua0011_ferry_stage_counter/tests/test_stage_counter_guard.py`

### `.github/workflows/task087_ua0011_korea_stage_production.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Короткий task-specific launcher/stub; после миграции сохранить только как историю.
- Referenced workflows: NONE
- Referenced scripts: NONE

### `.github/workflows/task089_crm_voice_photo_live_audit.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task089_crm_voice_photo_live_audit.yml`
- Referenced scripts: `cloud/task_089_crm_voice_photo_repair/evidence/live_audit.js`, `cloud/task_089_crm_voice_photo_repair/live_audit.py`

### `.github/workflows/task090_catalog_design_restore.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task090_catalog_design_restore.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_090_catalog_design_restore/catalog_design_guard.py`, `cloud/task_090_catalog_design_restore/controller.py`, `cloud/task_090_catalog_design_restore/evidence/deploy.js`, `cloud/task_090_catalog_design_restore/public_verify.py`, `cloud/task_090_catalog_design_restore/remote_installer.py`, `cloud/task_090_catalog_design_restore/test_catalog_design_guard.py`

### `.github/workflows/task091_numeric_claim_guard.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task091_numeric_claim_guard.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_091_numeric_claim_guard/controller.py`, `cloud/task_091_numeric_claim_guard/evidence/deploy.js`

### `.github/workflows/task092_anthropic_reset_autostart.yml`
- Decision: **ARCHIVE** → `uaart_fast.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: NONE
- Referenced scripts: `automation/claude_worker.py`

### `.github/workflows/task092_autostart.yml`
- Decision: **ARCHIVE** → `uaart_fast.yml`
- Rationale: Короткий task-specific launcher/stub; после миграции сохранить только как историю.
- Referenced workflows: NONE
- Referenced scripts: NONE

### `.github/workflows/task092_launch_after_limit.yml`
- Decision: **ARCHIVE** → `uaart_fast.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task092_launch_after_limit.yml`
- Referenced scripts: `automation/claude_worker.py`

### `.github/workflows/task093_home_stage_counter_sync_production.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task093_home_stage_counter_sync_production.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_093_home_stage_counter_sync/controller.py`, `cloud/task_093_home_stage_counter_sync/evidence/production.js`, `cloud/task_093_home_stage_counter_sync/home_counter_guard.py`, `cloud/task_093_home_stage_counter_sync/remote_installer.py`, `cloud/task_093_home_stage_counter_sync/test_home_counter_guard.py`

### `.github/workflows/task094_claude_autostart.yml`
- Decision: **ARCHIVE** → `uaart_rollback.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: NONE
- Referenced scripts: `automation/claude_worker.py`

### `.github/workflows/task095_catalog_visual_diagnostic.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task095_catalog_visual_diagnostic.yml`
- Referenced scripts: `automation/task095_visual_probe.py`, `cloud/task_095_catalog_visual_repair/evidence/browser_probe.js`

### `.github/workflows/task095_catalog_visual_repair.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task095_catalog_visual_repair.yml`
- Referenced scripts: `automation/task095_production_controller.py`, `automation/task095_visual_probe.py`, `cloud/task_095_catalog_visual_repair/evidence/browser_probe.js`, `cloud/task_095_catalog_visual_repair/evidence/browser_probe_delayed.js`, `cloud/task_095_catalog_visual_repair/evidence/browser_probe_immediate.js`, `cloud/task_095_catalog_visual_repair/evidence/final.js`, `cloud/task_095_catalog_visual_repair/remote_repair.py`

### `.github/workflows/task095_catalog_visual_repair_v2.yml`
- Decision: **ARCHIVE** → `uaart_backup.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task095_catalog_visual_repair_v2.yml`
- Referenced scripts: `automation/task095_production_controller_v2.py`, `automation/task095_visual_probe.py`, `cloud/task_095_catalog_visual_repair/evidence/browser_probe.js`, `cloud/task_095_catalog_visual_repair/evidence_v2/browser_probe_delayed.js`, `cloud/task_095_catalog_visual_repair/evidence_v2/browser_probe_immediate.js`, `cloud/task_095_catalog_visual_repair/evidence_v2/final.js`, `cloud/task_095_catalog_visual_repair/remote_repair_v2.py`

### `.github/workflows/task095_catalog_visual_repair_v3.yml`
- Decision: **ARCHIVE** → `uaart_backup.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task095_catalog_visual_repair_v3.yml`
- Referenced scripts: `automation/task095_production_controller_v3.py`, `automation/task095_visual_probe.py`, `cloud/task_095_catalog_visual_repair/evidence/browser_probe.js`, `cloud/task_095_catalog_visual_repair/evidence_v3/browser_probe_delayed.js`, `cloud/task_095_catalog_visual_repair/evidence_v3/browser_probe_immediate.js`, `cloud/task_095_catalog_visual_repair/evidence_v3/final.js`, `cloud/task_095_catalog_visual_repair/remote_repair_v3.py`

### `.github/workflows/task096_autorun_orchestrator.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task096_autorun_orchestrator.yml`
- Referenced scripts: `automation/task096_autorun_orchestrator.py`, `automation/task096_final_fix.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/state/task096_state.js`

### `.github/workflows/task096_claude_sandbox.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task096_claude_sandbox.yml`
- Referenced scripts: `automation/claude_worker.py`

### `.github/workflows/task096_controller_sandbox.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task096_controller_sandbox.yml`
- Referenced scripts: `automation/task096_pythonanywhere_controller.py`, `cloud/task_096_tech_spec_ai_crm/controller_evidence.js`, `cloud/task_096_tech_spec_ai_crm/dedup_check.py`, `cloud/task_096_tech_spec_ai_crm/manual_field_protection.py`, `cloud/task_096_tech_spec_ai_crm/price_exclusion_guard.py`, `cloud/task_096_tech_spec_ai_crm/selftest.py`, `cloud/task_096_tech_spec_ai_crm/source_check.py`, `cloud/task_096_tech_spec_ai_crm/task096_remote_controller.py`

### `.github/workflows/task096_data_enrichment_sandbox.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task096_data_enrichment_sandbox.yml`
- Referenced scripts: `automation/task096_data_enrichment_controller.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_apply.py`

### `.github/workflows/task096_enrichment_repair_v2.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task096_enrichment_repair_v2.yml`
- Referenced scripts: `automation/task096_enrichment_repair_v2.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py`

### `.github/workflows/task096_enrichment_repair_v3.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task096_enrichment_repair_v3.yml`
- Referenced scripts: `automation/task096_enrichment_repair_v2.py`, `automation/task096_enrichment_repair_v3.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py`

### `.github/workflows/task096_enrichment_repair_v4.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task096_enrichment_repair_v4.yml`
- Referenced scripts: `automation/task096_enrichment_repair_v2.py`, `automation/task096_enrichment_repair_v3.py`, `automation/task096_enrichment_repair_v4.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py`

### `.github/workflows/task096_enrichment_repair_v5.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task096_enrichment_repair_v5.yml`
- Referenced scripts: `automation/task096_data_enrichment_controller.py`, `automation/task096_enrichment_repair_v2.py`, `automation/task096_enrichment_repair_v3.py`, `automation/task096_enrichment_repair_v4.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py`

### `.github/workflows/task096_enrichment_repair_v6.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task096_enrichment_repair_v6.yml`
- Referenced scripts: `automation/task096_data_enrichment_controller.py`, `automation/task096_enrichment_repair_v2.py`, `automation/task096_enrichment_repair_v6.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py`

### `.github/workflows/task096_enrichment_repair_v7.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task096_enrichment_repair_v7.yml`
- Referenced scripts: `automation/task096_data_enrichment_controller.py`, `automation/task096_enrichment_repair_v2.py`, `automation/task096_enrichment_repair_v7.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py`

### `.github/workflows/task096_enrichment_repair_v8.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task096_enrichment_repair_v8.yml`
- Referenced scripts: `automation/task096_data_enrichment_controller.py`, `automation/task096_enrichment_repair_v2.py`, `automation/task096_enrichment_repair_v7.py`, `automation/task096_enrichment_repair_v8.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_apply.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py`

### `.github/workflows/task096_final_fix.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: NONE
- Referenced scripts: `automation/task096_final_fix.py`, `automation/task096_recovery10.py`, `automation/task096_recovery10_schema.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/recovery10_status.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/transport_diagnostic.js`

### `.github/workflows/task096_recovery10.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task096_recovery10.yml`
- Referenced scripts: `automation/task096_data_enrichment_controller.py`, `automation/task096_recovery10.py`, `automation/task096_recovery10_schema.py`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js`, `cloud/task_096_tech_spec_ai_crm/data_enrichment/recovery10_status.js`

### `.github/workflows/task096_repair_trigger.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: NONE
- Referenced scripts: NONE

### `.github/workflows/task097_editorial_atlas_audit.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/claude_autopilot.yml`, `.github/workflows/task097_editorial_atlas_audit.yml`
- Referenced scripts: `automation/claude_worker.py`, `cloud/task_097_editorial_atlas_news/evidence.js`

### `.github/workflows/task098_editorial_atlas_qa.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task098_editorial_atlas_qa.yml`
- Referenced scripts: `automation/claude_worker.py`, `cloud/task_097_editorial_atlas_news/evidence.js`, `cloud/task_098_editorial_atlas_qa/evidence_qa.js`, `cloud/task_098_editorial_atlas_qa/live_site_probe.js`, `cloud/task_098_editorial_atlas_qa/redirect_probe.js`, `cloud/task_098_editorial_atlas_qa/source_probe_qa_machine.js`

### `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- Decision: **ARCHIVE** → `uaart_standard.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- Referenced scripts: `automation/claude_worker.py`, `automation/task098_collect_context.py`, `automation/task098_run_validator.py`, `automation/task098_validate.py`, `cloud/task_097_editorial_atlas_news/evidence.js`, `cloud/task_098_editorial_atlas_qa/live_site_probe.js`, `cloud/task_098_editorial_atlas_qa/redirect_probe.js`, `cloud/task_098_editorial_atlas_qa/source_probe_qa_machine.js`

### `.github/workflows/task099_live_audit.yml`
- Decision: **MERGE** → `uaart_rollback.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task099_live_audit.yml`
- Referenced scripts: `automation/task099_live_audit.py`, `cloud/task_099_site_crm_repair/evidence/live_audit.js`, `cloud/task_099_site_crm_repair/evidence/source_bundle.js`

### `.github/workflows/task099_partial_recovery.yml`
- Decision: **ARCHIVE** → `uaart_rollback.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task099_partial_recovery.yml`
- Referenced scripts: `cloud/task_099_partial_recovery/task099_partial_recovery_controller.py`, `cloud/task_099_partial_recovery/task099_partial_recovery_remote.py`, `cloud/task_099_site_crm_repair/evidence/production_gate.js`, `cloud/task_099_site_crm_repair/evidence/visual_evidence.js`, `cloud/task_099_site_crm_repair/task099_finalize.py`, `cloud/task_099_site_crm_repair/task099_visual.py`

### `.github/workflows/task099_remote_state_probe.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task099_remote_state_probe.yml`
- Referenced scripts: NONE

### `.github/workflows/task099_site_crm_production.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task099_site_crm_production.yml`
- Referenced scripts: `cloud/task_093_home_stage_counter_sync/home_counter_guard.py`, `cloud/task_093_home_stage_counter_sync/test_home_counter_guard.py`, `cloud/task_099_site_crm_repair/evidence/production_gate.js`, `cloud/task_099_site_crm_repair/evidence/visual_evidence.js`, `cloud/task_099_site_crm_repair/task099_controller.py`, `cloud/task_099_site_crm_repair/task099_finalize.py`, `cloud/task_099_site_crm_repair/task099_patches.py`, `cloud/task_099_site_crm_repair/task099_remote.py`, `cloud/task_099_site_crm_repair/task099_visual.py`, `cloud/task_099_site_crm_repair/ua_additional_spec.py`

### `.github/workflows/task100_home_live_sync.yml`
- Decision: **MERGE** → `uaart_backup.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task100_home_live_sync.yml`
- Referenced scripts: `automation/production_queue.py`, `cloud/task_093_home_stage_counter_sync/home_counter_guard.py`, `cloud/task_093_home_stage_counter_sync/test_home_counter_guard.py`, `cloud/task_100_home_live_sync/controller.py`, `cloud/task_100_home_live_sync/evidence.js`, `cloud/task_100_home_live_sync/remote_patch.py`

### `.github/workflows/task102_seo_audit.yml`
- Decision: **MERGE** → `uaart_standard.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task102_seo_audit.yml`
- Referenced scripts: `cloud/seo_korea_kyiv_001/evidence/read_only_audit.js`, `cloud/seo_korea_kyiv_001/seo_korea_kyiv_001.py`

### `.github/workflows/task102_seo_routing_probe.yml`
- Decision: **MERGE** → `uaart_monitor.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task102_seo_routing_probe.yml`
- Referenced scripts: NONE

### `.github/workflows/task103_ge_8country_sandbox_autostart.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: NONE
- Referenced scripts: `automation/claude_worker.py`

### `.github/workflows/task104_canary_recovery.yml`
- Decision: **ARCHIVE** → `uaart_fast.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: NONE
- Referenced scripts: NONE

### `.github/workflows/task104_canary_worker.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: NONE
- Referenced scripts: `automation/task104_canary_worker.py`, `automation/task104_self_recovery_core.py`

### `.github/workflows/task104_integration_canary.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task104_integration_canary.yml`
- Referenced scripts: `cloud/task104_self_recovery/state/task104_integration_report.js`

### `.github/workflows/task104_self_recovery_sandbox.yml`
- Decision: **ARCHIVE** → `uaart_critical.yml`
- Rationale: Версионный/retry/autostart task-specific workflow; высокая вероятность superseded-дублирования.
- Referenced workflows: `.github/workflows/task104_self_recovery_sandbox.yml`
- Referenced scripts: `automation/task104_self_recovery_core.py`, `automation/task104_self_recovery_suite.py`, `cloud/task104_self_recovery/state/task104_report.js`

### `.github/workflows/task105_phase0_audit.yml`
- Decision: **MERGE** → `uaart_critical.yml`
- Rationale: Task-specific workflow должен стать параметром общего конвейера.
- Referenced workflows: `.github/workflows/task105_phase0_audit.yml`
- Referenced scripts: `cloud/task_105_fast_pipeline_phase0/phase0_audit.py`

### `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml`
- Decision: **ARCHIVE** → `uaart_rollback.yml`
- Rationale: Версионный инфраструктурный вариант; проверить преемника и затем архивировать.
- Referenced workflows: `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml`
- Referenced scripts: `automation/autopilot_core_v2.py`, `cloud/autopilot_core_v2/state/failure_injection_report.js`, `cloud/autopilot_core_v2/state/queue.js`
