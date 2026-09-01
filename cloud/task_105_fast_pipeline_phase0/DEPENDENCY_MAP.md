# DEPENDENCY MAP — TASK105

## Control-plane flow observed

```text
Owner/ChatGPT → tasks/task_NNN.md → GitHub workflow → deterministic scripts and/or Claude
→ cloud outputs / evidence → PythonAnywhere transport (where explicitly enabled)
→ production transaction → live verification / rollback
```

## High-risk capability groups

### Production-write capable (107)
- `.github/workflows/claude_autopilot.yml`
- `.github/workflows/ferry_wording_gate_a.yml`
- `.github/workflows/ferry_wording_gate_b.yml`
- `.github/workflows/overnight_autopilot_production_dispatch.yml`
- `.github/workflows/overnight_task099_transient_recovery.yml`
- `.github/workflows/owner_ua0011_full_card_gate_a.yml`
- `.github/workflows/owner_ua0011_korea_now_production.yml`
- `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `.github/workflows/safe_workflow_watchdog.yml`
- `.github/workflows/seo-rehab-068-production.yml`
- `.github/workflows/task049_gate_b.yml`
- `.github/workflows/task049_gate_b_preflight.yml`
- `.github/workflows/task059_ai_fast_schema.yml`
- `.github/workflows/task060_install_token_free_ocr.yml`
- `.github/workflows/task060_read_live_context.yml`
- `.github/workflows/task061_crm_ai_card.yml`
- `.github/workflows/task062_crm_voice.yml`
- `.github/workflows/task062_read_voice_context.yml`
- `.github/workflows/task064_crm_db_lock_hotfix.yml`
- `.github/workflows/task064_diagnostics_permanent.yml`
- `.github/workflows/task064_read_crm_lock_context.yml`
- `.github/workflows/task065_crm_photo_fastpath.yml`
- `.github/workflows/task066_stage_anchor_deploy.yml`
- `.github/workflows/task066_stage_anchor_probe.yml`
- `.github/workflows/task067_crm_online_guard_deploy.yml`
- `.github/workflows/task067_health_probe.yml`
- `.github/workflows/task067_read_only_audit.yml`
- `.github/workflows/task068_catalog_structure_probe.yml`
- `.github/workflows/task068_ferry_vin_deploy.yml`
- `.github/workflows/task068_ferry_vin_probe.yml`
- `.github/workflows/task069_crm_container_gate_a.yml`
- `.github/workflows/task069_crm_container_gate_b.yml`
- `.github/workflows/task069_crm_container_readonly.yml`
- `.github/workflows/task070_real_context_probe.yml`
- `.github/workflows/task071_call_path_read.yml`
- `.github/workflows/task072_gate_a_v2.yml`
- `.github/workflows/task072_gate_b.yml`
- `.github/workflows/task073_gate_a_live_probe.yml`
- `.github/workflows/task073_gate_a_v5.yml`
- `.github/workflows/task073_gate_b_v5.yml`
- `.github/workflows/task074_catalog_card_unify.yml`
- `.github/workflows/task075_stage_guard_sandbox.yml`
- `.github/workflows/task076_eta_gate_a_live.yml`
- `.github/workflows/task077_container_stage_sync_gate_a.yml`
- `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `.github/workflows/task078_voice_watchdog_gate_a.yml`
- `.github/workflows/task080_price_candidate.yml`
- `.github/workflows/task080_price_gate_a.yml`
- `.github/workflows/task081_publish_repair_gate_a_v2.yml`
- `.github/workflows/task081_publish_repair_gate_b_v2.yml`
- `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `.github/workflows/task082_audit_probe.yml`
- `.github/workflows/task082_audit_probe_persist.yml`
- `.github/workflows/task082_catalog_stage_production.yml`
- `.github/workflows/task082_live_source_probe.yml`
- `.github/workflows/task082_source_probe_persist.yml`
- `.github/workflows/task082_vin4_title_deploy.yml`
- `.github/workflows/task082_vin4_title_production.yml`
- `.github/workflows/task083_catalog_dedup.yml`
- `.github/workflows/task083_production_hold.yml`
- `.github/workflows/task083_publish_transaction.yml`
- `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
- `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `.github/workflows/task084_korea_reset_gate_a.yml`
- `.github/workflows/task085_stage_payload_reset_production.yml`
- `.github/workflows/task086_public_catalog_readonly_probe.yml`
- `.github/workflows/task086_renderer_gate_a.yml`
- `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
- `.github/workflows/task087_ua0011_korea_stage_production.yml`
- `.github/workflows/task089_crm_voice_photo_live_audit.yml`
- `.github/workflows/task090_catalog_design_restore.yml`
- `.github/workflows/task091_numeric_claim_guard.yml`
- `.github/workflows/task093_home_stage_counter_sync_production.yml`
- `.github/workflows/task094_claude_autostart.yml`
- `.github/workflows/task095_catalog_visual_diagnostic.yml`
- `.github/workflows/task095_catalog_visual_repair.yml`
- `.github/workflows/task095_catalog_visual_repair_v2.yml`
- `.github/workflows/task095_catalog_visual_repair_v3.yml`
- `.github/workflows/task096_autorun_orchestrator.yml`
- `.github/workflows/task096_claude_sandbox.yml`
- `.github/workflows/task096_controller_sandbox.yml`
- `.github/workflows/task096_data_enrichment_sandbox.yml`
- `.github/workflows/task096_enrichment_repair_v2.yml`
- `.github/workflows/task096_enrichment_repair_v3.yml`
- `.github/workflows/task096_enrichment_repair_v4.yml`
- `.github/workflows/task096_enrichment_repair_v5.yml`
- `.github/workflows/task096_enrichment_repair_v6.yml`
- `.github/workflows/task096_enrichment_repair_v7.yml`
- `.github/workflows/task096_enrichment_repair_v8.yml`
- `.github/workflows/task096_final_fix.yml`
- `.github/workflows/task096_recovery10.yml`
- `.github/workflows/task096_repair_trigger.yml`
- `.github/workflows/task097_editorial_atlas_audit.yml`
- `.github/workflows/task098_editorial_atlas_qa.yml`
- `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- `.github/workflows/task099_live_audit.yml`
- `.github/workflows/task099_partial_recovery.yml`
- `.github/workflows/task099_remote_state_probe.yml`
- `.github/workflows/task099_site_crm_production.yml`
- `.github/workflows/task100_home_live_sync.yml`
- `.github/workflows/task102_seo_audit.yml`
- `.github/workflows/task103_ge_8country_sandbox_autostart.yml`
- `.github/workflows/task104_canary_worker.yml`
- `.github/workflows/task104_integration_canary.yml`
- `.github/workflows/task104_self_recovery_sandbox.yml`
- `.github/workflows/task105_phase0_audit.yml`
- `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml`

### PythonAnywhere transport (109)
- `.github/workflows/ferry_wording_gate_a.yml`
- `.github/workflows/ferry_wording_gate_b.yml`
- `.github/workflows/overnight_task099_transient_recovery.yml`
- `.github/workflows/owner_ua0011_full_card_gate_a.yml`
- `.github/workflows/owner_ua0011_korea_now_production.yml`
- `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `.github/workflows/pythonanywhere_sync.yml`
- `.github/workflows/safe_workflow_watchdog.yml`
- `.github/workflows/seo-rehab-068-production.yml`
- `.github/workflows/task037_discovery.yml`
- `.github/workflows/task039_retry.yml`
- `.github/workflows/task039_safe_inbox_sync.yml`
- `.github/workflows/task049_gate_a.yml`
- `.github/workflows/task049_gate_b.yml`
- `.github/workflows/task049_gate_b_preflight.yml`
- `.github/workflows/task058_crm_ocr_readonly.yml`
- `.github/workflows/task059_ai_fast_schema.yml`
- `.github/workflows/task060_install_token_free_ocr.yml`
- `.github/workflows/task060_read_live_context.yml`
- `.github/workflows/task060_runtime_capabilities.yml`
- `.github/workflows/task061_crm_ai_card.yml`
- `.github/workflows/task062_crm_voice.yml`
- `.github/workflows/task062_read_voice_context.yml`
- `.github/workflows/task064_crm_db_lock_hotfix.yml`
- `.github/workflows/task064_diagnostics_permanent.yml`
- `.github/workflows/task064_emergency_crm_quiesce.yml`
- `.github/workflows/task064_read_crm_lock_context.yml`
- `.github/workflows/task064_trace_wrapper_probe.yml`
- `.github/workflows/task065_counter_v2_hotfix.yml`
- `.github/workflows/task065_crm_photo_fastpath.yml`
- `.github/workflows/task065_photo_path_probe.yml`
- `.github/workflows/task065_ua0011_probe.yml`
- `.github/workflows/task065_voice_path_probe.yml`
- `.github/workflows/task066_stage_anchor_deploy.yml`
- `.github/workflows/task066_stage_anchor_probe.yml`
- `.github/workflows/task067_crm_online_guard_deploy.yml`
- `.github/workflows/task067_health_probe.yml`
- `.github/workflows/task067_read_only_audit.yml`
- `.github/workflows/task068_catalog_structure_probe.yml`
- `.github/workflows/task068_ferry_vin_deploy.yml`
- `.github/workflows/task068_ferry_vin_probe.yml`
- `.github/workflows/task069_crm_container_gate_a.yml`
- `.github/workflows/task069_crm_container_gate_b.yml`
- `.github/workflows/task069_crm_container_readonly.yml`
- `.github/workflows/task070_real_context_probe.yml`
- `.github/workflows/task071_call_path_read.yml`
- `.github/workflows/task072_gate_a_v2.yml`
- `.github/workflows/task072_gate_b.yml`
- `.github/workflows/task073_gate_a_live_probe.yml`
- `.github/workflows/task073_gate_a_v5.yml`
- `.github/workflows/task073_gate_b_v5.yml`
- `.github/workflows/task074_catalog_card_unify.yml`
- `.github/workflows/task075_stage_guard_sandbox.yml`
- `.github/workflows/task076_eta_gate_a_live.yml`
- `.github/workflows/task077_container_stage_sync_gate_a.yml`
- `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `.github/workflows/task078_voice_watchdog_gate_a.yml`
- `.github/workflows/task080_price_candidate.yml`
- `.github/workflows/task080_price_gate_a.yml`
- `.github/workflows/task081_publish_repair_gate_a_v2.yml`
- `.github/workflows/task081_publish_repair_gate_b_v2.yml`
- `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `.github/workflows/task082_audit_probe.yml`
- `.github/workflows/task082_audit_probe_persist.yml`
- `.github/workflows/task082_live_source_probe.yml`
- `.github/workflows/task082_source_probe_persist.yml`
- `.github/workflows/task082_stage_probe.yml`
- `.github/workflows/task082_vin4_title_deploy.yml`
- `.github/workflows/task082_vin4_title_production.yml`
- `.github/workflows/task083_catalog_dedup.yml`
- `.github/workflows/task083_publish_transaction.yml`
- `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
- `.github/workflows/task084_crm_hang_root_cause.yml`
- `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `.github/workflows/task084_gate_a_live_read_only.yml`
- `.github/workflows/task084_korea_reset_gate_a.yml`
- `.github/workflows/task085_stage_payload_reset_production.yml`
- `.github/workflows/task086_renderer_gate_a.yml`
- `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
- `.github/workflows/task087_ua0011_korea_stage_production.yml`
- `.github/workflows/task089_crm_voice_photo_live_audit.yml`
- `.github/workflows/task090_catalog_design_restore.yml`
- `.github/workflows/task091_numeric_claim_guard.yml`
- `.github/workflows/task093_home_stage_counter_sync_production.yml`
- `.github/workflows/task095_catalog_visual_repair.yml`
- `.github/workflows/task095_catalog_visual_repair_v2.yml`
- `.github/workflows/task095_catalog_visual_repair_v3.yml`
- `.github/workflows/task096_autorun_orchestrator.yml`
- `.github/workflows/task096_controller_sandbox.yml`
- `.github/workflows/task096_data_enrichment_sandbox.yml`
- `.github/workflows/task096_enrichment_repair_v2.yml`
- `.github/workflows/task096_enrichment_repair_v3.yml`
- `.github/workflows/task096_enrichment_repair_v4.yml`
- `.github/workflows/task096_enrichment_repair_v5.yml`
- `.github/workflows/task096_enrichment_repair_v6.yml`
- `.github/workflows/task096_enrichment_repair_v7.yml`
- `.github/workflows/task096_enrichment_repair_v8.yml`
- `.github/workflows/task096_final_fix.yml`
- `.github/workflows/task096_recovery10.yml`
- `.github/workflows/task097_editorial_atlas_audit.yml`
- `.github/workflows/task099_live_audit.yml`
- `.github/workflows/task099_partial_recovery.yml`
- `.github/workflows/task099_remote_state_probe.yml`
- `.github/workflows/task099_site_crm_production.yml`
- `.github/workflows/task100_home_live_sync.yml`
- `.github/workflows/task102_seo_audit.yml`
- `.github/workflows/task102_seo_routing_probe.yml`
- `.github/workflows/task105_phase0_audit.yml`
- `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml`

### Anthropic/Claude (22)
- `.github/workflows/claude_autopilot.yml`
- `.github/workflows/task039_retry.yml`
- `.github/workflows/task092_anthropic_reset_autostart.yml`
- `.github/workflows/task092_autostart.yml`
- `.github/workflows/task092_launch_after_limit.yml`
- `.github/workflows/task094_claude_autostart.yml`
- `.github/workflows/task096_autorun_orchestrator.yml`
- `.github/workflows/task096_claude_sandbox.yml`
- `.github/workflows/task096_data_enrichment_sandbox.yml`
- `.github/workflows/task096_enrichment_repair_v2.yml`
- `.github/workflows/task096_enrichment_repair_v3.yml`
- `.github/workflows/task096_enrichment_repair_v4.yml`
- `.github/workflows/task096_enrichment_repair_v5.yml`
- `.github/workflows/task096_enrichment_repair_v6.yml`
- `.github/workflows/task096_enrichment_repair_v7.yml`
- `.github/workflows/task096_enrichment_repair_v8.yml`
- `.github/workflows/task096_final_fix.yml`
- `.github/workflows/task096_recovery10.yml`
- `.github/workflows/task097_editorial_atlas_audit.yml`
- `.github/workflows/task098_editorial_atlas_qa.yml`
- `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- `.github/workflows/task103_ge_8country_sandbox_autostart.yml`

### Watchdog/health (4)
- `.github/workflows/safe_workflow_watchdog.yml`
- `.github/workflows/task078_voice_watchdog_gate_a.yml`
- `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
- `.github/workflows/task084_crm_hang_root_cause_production.yml`

### Queue gate (9)
- `.github/workflows/owner_ua0011_korea_now_production.yml`
- `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `.github/workflows/task083_publish_transaction.yml`
- `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
- `.github/workflows/task090_catalog_design_restore.yml`
- `.github/workflows/task091_numeric_claim_guard.yml`
- `.github/workflows/task093_home_stage_counter_sync_production.yml`
- `.github/workflows/task100_home_live_sync.yml`

### Retry/recovery (104)
- `.github/workflows/claude_autopilot.yml`
- `.github/workflows/ferry_wording_gate_a.yml`
- `.github/workflows/ferry_wording_gate_b.yml`
- `.github/workflows/overnight_task099_transient_recovery.yml`
- `.github/workflows/owner_ua0011_full_card_gate_a.yml`
- `.github/workflows/owner_ua0011_korea_now_production.yml`
- `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `.github/workflows/safe_workflow_watchdog.yml`
- `.github/workflows/seo-rehab-068-production.yml`
- `.github/workflows/seo-watch-smoke.yml`
- `.github/workflows/task037_discovery.yml`
- `.github/workflows/task039_retry.yml`
- `.github/workflows/task039_safe_inbox_sync.yml`
- `.github/workflows/task049_gate_a.yml`
- `.github/workflows/task049_gate_b.yml`
- `.github/workflows/task049_gate_b_preflight.yml`
- `.github/workflows/task058_crm_ocr_readonly.yml`
- `.github/workflows/task059_ai_fast_schema.yml`
- `.github/workflows/task060_install_token_free_ocr.yml`
- `.github/workflows/task060_read_live_context.yml`
- `.github/workflows/task060_runtime_capabilities.yml`
- `.github/workflows/task061_crm_ai_card.yml`
- `.github/workflows/task062_crm_voice.yml`
- `.github/workflows/task062_read_voice_context.yml`
- `.github/workflows/task064_crm_db_lock_hotfix.yml`
- `.github/workflows/task064_diagnostics_permanent.yml`
- `.github/workflows/task064_emergency_crm_quiesce.yml`
- `.github/workflows/task064_read_crm_lock_context.yml`
- `.github/workflows/task064_trace_wrapper_probe.yml`
- `.github/workflows/task065_counter_v2_hotfix.yml`
- `.github/workflows/task065_crm_photo_fastpath.yml`
- `.github/workflows/task065_photo_path_probe.yml`
- `.github/workflows/task065_ua0011_probe.yml`
- `.github/workflows/task065_voice_path_probe.yml`
- `.github/workflows/task066_stage_anchor_deploy.yml`
- `.github/workflows/task066_stage_anchor_probe.yml`
- `.github/workflows/task067_crm_online_guard_deploy.yml`
- `.github/workflows/task067_read_only_audit.yml`
- `.github/workflows/task068_catalog_structure_probe.yml`
- `.github/workflows/task068_ferry_vin_deploy.yml`
- `.github/workflows/task068_ferry_vin_probe.yml`
- `.github/workflows/task069_crm_container_gate_a.yml`
- `.github/workflows/task069_crm_container_gate_b.yml`
- `.github/workflows/task069_crm_container_readonly.yml`
- `.github/workflows/task070_real_context_probe.yml`
- `.github/workflows/task071_call_path_read.yml`
- `.github/workflows/task072_gate_a_v2.yml`
- `.github/workflows/task072_gate_b.yml`
- `.github/workflows/task073_gate_a_live_probe.yml`
- `.github/workflows/task074_catalog_card_unify.yml`
- `.github/workflows/task075_stage_guard_sandbox.yml`
- `.github/workflows/task076_eta_gate_a_live.yml`
- `.github/workflows/task077_container_stage_sync_gate_a.yml`
- `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `.github/workflows/task078_voice_watchdog_gate_a.yml`
- `.github/workflows/task080_price_gate_a.yml`
- `.github/workflows/task081_publish_repair_gate_a_v2.yml`
- `.github/workflows/task082_audit_probe_persist.yml`
- `.github/workflows/task082_live_source_probe.yml`
- `.github/workflows/task082_source_probe_persist.yml`
- `.github/workflows/task082_stage_probe.yml`
- `.github/workflows/task082_vin4_title_deploy.yml`
- `.github/workflows/task082_vin4_title_production.yml`
- `.github/workflows/task083_catalog_dedup.yml`
- `.github/workflows/task083_publish_transaction.yml`
- `.github/workflows/task084_crm_hang_root_cause.yml`
- `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `.github/workflows/task084_gate_a_live_read_only.yml`
- `.github/workflows/task084_korea_reset_gate_a.yml`
- `.github/workflows/task086_renderer_gate_a.yml`
- `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
- `.github/workflows/task089_crm_voice_photo_live_audit.yml`
- `.github/workflows/task090_catalog_design_restore.yml`
- `.github/workflows/task091_numeric_claim_guard.yml`
- `.github/workflows/task092_anthropic_reset_autostart.yml`
- `.github/workflows/task092_autostart.yml`
- `.github/workflows/task092_launch_after_limit.yml`
- `.github/workflows/task093_home_stage_counter_sync_production.yml`
- `.github/workflows/task094_claude_autostart.yml`
- `.github/workflows/task095_catalog_visual_diagnostic.yml`
- `.github/workflows/task095_catalog_visual_repair.yml`
- `.github/workflows/task095_catalog_visual_repair_v2.yml`
- `.github/workflows/task096_autorun_orchestrator.yml`
- `.github/workflows/task096_claude_sandbox.yml`
- `.github/workflows/task096_controller_sandbox.yml`
- `.github/workflows/task096_data_enrichment_sandbox.yml`
- `.github/workflows/task096_enrichment_repair_v2.yml`
- `.github/workflows/task096_enrichment_repair_v7.yml`
- `.github/workflows/task096_enrichment_repair_v8.yml`
- `.github/workflows/task096_final_fix.yml`
- `.github/workflows/task096_recovery10.yml`
- `.github/workflows/task096_repair_trigger.yml`
- `.github/workflows/task097_editorial_atlas_audit.yml`
- `.github/workflows/task098_editorial_atlas_qa.yml`
- `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- `.github/workflows/task099_live_audit.yml`
- `.github/workflows/task099_partial_recovery.yml`
- `.github/workflows/task099_site_crm_production.yml`
- `.github/workflows/task103_ge_8country_sandbox_autostart.yml`
- `.github/workflows/task104_canary_recovery.yml`
- `.github/workflows/task104_canary_worker.yml`
- `.github/workflows/task104_integration_canary.yml`
- `.github/workflows/task104_self_recovery_sandbox.yml`
- `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml`

## Shared scripts by number of workflow callers

- `cloud/task_096_tech_spec_ai_crm/data_enrichment/evidence.js` ← 12 workflows
  - `.github/workflows/overnight_autopilot_production_dispatch.yml`
  - `.github/workflows/task096_autorun_orchestrator.yml`
  - `.github/workflows/task096_data_enrichment_sandbox.yml`
  - `.github/workflows/task096_enrichment_repair_v2.yml`
  - `.github/workflows/task096_enrichment_repair_v3.yml`
  - `.github/workflows/task096_enrichment_repair_v4.yml`
  - `.github/workflows/task096_enrichment_repair_v5.yml`
  - `.github/workflows/task096_enrichment_repair_v6.yml`
  - `.github/workflows/task096_enrichment_repair_v7.yml`
  - `.github/workflows/task096_enrichment_repair_v8.yml`
  - `.github/workflows/task096_final_fix.yml`
  - `.github/workflows/task096_recovery10.yml`
- `cloud/task_096_tech_spec_ai_crm/data_enrichment/cards_summary.js` ← 11 workflows
  - `.github/workflows/task096_autorun_orchestrator.yml`
  - `.github/workflows/task096_data_enrichment_sandbox.yml`
  - `.github/workflows/task096_enrichment_repair_v2.yml`
  - `.github/workflows/task096_enrichment_repair_v3.yml`
  - `.github/workflows/task096_enrichment_repair_v4.yml`
  - `.github/workflows/task096_enrichment_repair_v5.yml`
  - `.github/workflows/task096_enrichment_repair_v6.yml`
  - `.github/workflows/task096_enrichment_repair_v7.yml`
  - `.github/workflows/task096_enrichment_repair_v8.yml`
  - `.github/workflows/task096_final_fix.yml`
  - `.github/workflows/task096_recovery10.yml`
- `automation/claude_worker.py` ← 9 workflows
  - `.github/workflows/claude_autopilot.yml`
  - `.github/workflows/task092_anthropic_reset_autostart.yml`
  - `.github/workflows/task092_launch_after_limit.yml`
  - `.github/workflows/task094_claude_autostart.yml`
  - `.github/workflows/task096_claude_sandbox.yml`
  - `.github/workflows/task097_editorial_atlas_audit.yml`
  - `.github/workflows/task098_editorial_atlas_qa.yml`
  - `.github/workflows/task098_editorial_atlas_qa_retry.yml`
  - `.github/workflows/task103_ge_8country_sandbox_autostart.yml`
- `automation/production_queue.py` ← 9 workflows
  - `.github/workflows/owner_ua0011_korea_now_production.yml`
  - `.github/workflows/owner_ua0011_korea_slim_production.yml`
  - `.github/workflows/task083_publish_transaction.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
  - `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
  - `.github/workflows/task090_catalog_design_restore.yml`
  - `.github/workflows/task091_numeric_claim_guard.yml`
  - `.github/workflows/task093_home_stage_counter_sync_production.yml`
  - `.github/workflows/task100_home_live_sync.yml`
- `automation/task096_enrichment_repair_v2.py` ← 7 workflows
  - `.github/workflows/task096_enrichment_repair_v2.yml`
  - `.github/workflows/task096_enrichment_repair_v3.yml`
  - `.github/workflows/task096_enrichment_repair_v4.yml`
  - `.github/workflows/task096_enrichment_repair_v5.yml`
  - `.github/workflows/task096_enrichment_repair_v6.yml`
  - `.github/workflows/task096_enrichment_repair_v7.yml`
  - `.github/workflows/task096_enrichment_repair_v8.yml`
- `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_semantic_cleanup.py` ← 7 workflows
  - `.github/workflows/task096_enrichment_repair_v2.yml`
  - `.github/workflows/task096_enrichment_repair_v3.yml`
  - `.github/workflows/task096_enrichment_repair_v4.yml`
  - `.github/workflows/task096_enrichment_repair_v5.yml`
  - `.github/workflows/task096_enrichment_repair_v6.yml`
  - `.github/workflows/task096_enrichment_repair_v7.yml`
  - `.github/workflows/task096_enrichment_repair_v8.yml`
- `automation/task096_data_enrichment_controller.py` ← 6 workflows
  - `.github/workflows/task096_data_enrichment_sandbox.yml`
  - `.github/workflows/task096_enrichment_repair_v5.yml`
  - `.github/workflows/task096_enrichment_repair_v6.yml`
  - `.github/workflows/task096_enrichment_repair_v7.yml`
  - `.github/workflows/task096_enrichment_repair_v8.yml`
  - `.github/workflows/task096_recovery10.yml`
- `automation/task095_visual_probe.py` ← 4 workflows
  - `.github/workflows/task095_catalog_visual_diagnostic.yml`
  - `.github/workflows/task095_catalog_visual_repair.yml`
  - `.github/workflows/task095_catalog_visual_repair_v2.yml`
  - `.github/workflows/task095_catalog_visual_repair_v3.yml`
- `cloud/task_075_stage_guard/stage_guard.py` ← 4 workflows
  - `.github/workflows/task075_stage_guard_sandbox.yml`
  - `.github/workflows/task083_catalog_dedup.yml`
  - `.github/workflows/task083_publish_transaction.yml`
  - `.github/workflows/task084_korea_reset_gate_a.yml`
- `cloud/task_095_catalog_visual_repair/evidence/browser_probe.js` ← 4 workflows
  - `.github/workflows/task095_catalog_visual_diagnostic.yml`
  - `.github/workflows/task095_catalog_visual_repair.yml`
  - `.github/workflows/task095_catalog_visual_repair_v2.yml`
  - `.github/workflows/task095_catalog_visual_repair_v3.yml`
- `automation/task096_enrichment_repair_v3.py` ← 3 workflows
  - `.github/workflows/task096_enrichment_repair_v3.yml`
  - `.github/workflows/task096_enrichment_repair_v4.yml`
  - `.github/workflows/task096_enrichment_repair_v5.yml`
- `cloud/task_078_voice_watchdog/handler_patcher.py` ← 3 workflows
  - `.github/workflows/task078_voice_watchdog_gate_a.yml`
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_078_voice_watchdog/tests/test_handler_patcher.py` ← 3 workflows
  - `.github/workflows/task078_voice_watchdog_gate_a.yml`
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_078_voice_watchdog/tests/test_voice_watchdog.py` ← 3 workflows
  - `.github/workflows/task078_voice_watchdog_gate_a.yml`
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_078_voice_watchdog/voice_watchdog.py` ← 3 workflows
  - `.github/workflows/task078_voice_watchdog_gate_a.yml`
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_084_crm_hang_root_cause/evidence/live_audit.js` ← 3 workflows
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_084_crm_hang_root_cause/live_audit.py` ← 3 workflows
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_093_home_stage_counter_sync/home_counter_guard.py` ← 3 workflows
  - `.github/workflows/task093_home_stage_counter_sync_production.yml`
  - `.github/workflows/task099_site_crm_production.yml`
  - `.github/workflows/task100_home_live_sync.yml`
- `cloud/task_093_home_stage_counter_sync/test_home_counter_guard.py` ← 3 workflows
  - `.github/workflows/task093_home_stage_counter_sync_production.yml`
  - `.github/workflows/task099_site_crm_production.yml`
  - `.github/workflows/task100_home_live_sync.yml`
- `cloud/task_097_editorial_atlas_news/evidence.js` ← 3 workflows
  - `.github/workflows/task097_editorial_atlas_audit.yml`
  - `.github/workflows/task098_editorial_atlas_qa.yml`
  - `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- `automation/pythonanywhere_sync_v2.py` ← 2 workflows
  - `.github/workflows/pythonanywhere_sync.yml`
  - `.github/workflows/task039_safe_inbox_sync.yml`
- `automation/task096_enrichment_repair_v4.py` ← 2 workflows
  - `.github/workflows/task096_enrichment_repair_v4.yml`
  - `.github/workflows/task096_enrichment_repair_v5.yml`
- `automation/task096_enrichment_repair_v7.py` ← 2 workflows
  - `.github/workflows/task096_enrichment_repair_v7.yml`
  - `.github/workflows/task096_enrichment_repair_v8.yml`
- `automation/task096_final_fix.py` ← 2 workflows
  - `.github/workflows/task096_autorun_orchestrator.yml`
  - `.github/workflows/task096_final_fix.yml`
- `automation/task096_recovery10.py` ← 2 workflows
  - `.github/workflows/task096_final_fix.yml`
  - `.github/workflows/task096_recovery10.yml`
- `automation/task096_recovery10_schema.py` ← 2 workflows
  - `.github/workflows/task096_final_fix.yml`
  - `.github/workflows/task096_recovery10.yml`
- `automation/task104_self_recovery_core.py` ← 2 workflows
  - `.github/workflows/task104_canary_worker.yml`
  - `.github/workflows/task104_self_recovery_sandbox.yml`
- `cloud/bot_logistics/pythonanywhere_discovery_controller.py` ← 2 workflows
  - `.github/workflows/task037_discovery.yml`
  - `.github/workflows/task039_retry.yml`
- `cloud/task_047_ferry_discovery/run_tests.py` ← 2 workflows
  - `.github/workflows/ferry_wording_gate_a.yml`
  - `.github/workflows/ferry_wording_gate_b.yml`
- `cloud/task_061/local_ocr.py` ← 2 workflows
  - `.github/workflows/task061_crm_ai_card.yml`
  - `.github/workflows/task062_crm_voice.yml`
- `cloud/task_072/crm_description_writer_v2.py` ← 2 workflows
  - `.github/workflows/task072_gate_a_v2.yml`
  - `.github/workflows/task072_gate_b.yml`
- `cloud/task_072/evidence/gate_a_v2.js` ← 2 workflows
  - `.github/workflows/task072_gate_a_v2.yml`
  - `.github/workflows/task072_gate_b.yml`
- `cloud/task_072/gate_b_controller_v2.py` ← 2 workflows
  - `.github/workflows/task072_gate_a_v2.yml`
  - `.github/workflows/task072_gate_b.yml`
- `cloud/task_072/installer_v2.py` ← 2 workflows
  - `.github/workflows/task072_gate_a_v2.yml`
  - `.github/workflows/task072_gate_b.yml`
- `cloud/task_072/patch_cars_ui_v2.py` ← 2 workflows
  - `.github/workflows/task072_gate_a_v2.yml`
  - `.github/workflows/task072_gate_b.yml`
- `cloud/task_072/postcheck_v2.py` ← 2 workflows
  - `.github/workflows/task072_gate_a_v2.yml`
  - `.github/workflows/task072_gate_b.yml`
- `cloud/task_073/evidence/gate_a_v5.js` ← 2 workflows
  - `.github/workflows/task073_gate_a_v5.yml`
  - `.github/workflows/task073_gate_b_v5.yml`
- `cloud/task_076_eta_sync/eta_engine.py` ← 2 workflows
  - `.github/workflows/task077_container_stage_sync_gate_a.yml`
  - `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `cloud/task_077_container_stage_sync/gate_b/controller.py` ← 2 workflows
  - `.github/workflows/task077_container_stage_sync_gate_a.yml`
  - `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `cloud/task_077_container_stage_sync/gate_b/remote.py` ← 2 workflows
  - `.github/workflows/task077_container_stage_sync_gate_a.yml`
  - `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `cloud/task_077_container_stage_sync/patcher/eta_release_candidate.py` ← 2 workflows
  - `.github/workflows/task077_container_stage_sync_gate_a.yml`
  - `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `cloud/task_077_container_stage_sync/patcher/live_patcher.py` ← 2 workflows
  - `.github/workflows/task077_container_stage_sync_gate_a.yml`
  - `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `cloud/task_077_container_stage_sync/tests/test_eta_release_candidate.py` ← 2 workflows
  - `.github/workflows/task077_container_stage_sync_gate_a.yml`
  - `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `cloud/task_077_container_stage_sync/tests/test_gate_b_release.py` ← 2 workflows
  - `.github/workflows/task077_container_stage_sync_gate_a.yml`
  - `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `cloud/task_080_price_recognition/src/price_parser.py` ← 2 workflows
  - `.github/workflows/task080_price_candidate.yml`
  - `.github/workflows/task080_price_gate_a.yml`
- `cloud/task_080_price_recognition/tests/test_price_parser.py` ← 2 workflows
  - `.github/workflows/task080_price_candidate.yml`
  - `.github/workflows/task080_price_gate_a.yml`
- `cloud/task_081_publish_repair/evidence/gate_a_v2.js` ← 2 workflows
  - `.github/workflows/task081_publish_repair_gate_b_v2.yml`
  - `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `cloud/task_081_publish_repair/evidence/live_audit_v2/live_audit.js` ← 2 workflows
  - `.github/workflows/task081_publish_repair_gate_b_v2.yml`
  - `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `cloud/task_081_publish_repair/gate_a_v2.py` ← 2 workflows
  - `.github/workflows/task081_publish_repair_gate_b_v2.yml`
  - `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `cloud/task_081_publish_repair/live_audit_v2.py` ← 2 workflows
  - `.github/workflows/task081_publish_repair_gate_b_v2.yml`
  - `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `cloud/task_081_publish_repair/test_gate_b_v2.py` ← 2 workflows
  - `.github/workflows/task081_publish_repair_gate_b_v2.yml`
  - `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `cloud/task_081_publish_repair/test_release_candidate_v2.py` ← 2 workflows
  - `.github/workflows/task081_publish_repair_gate_b_v2.yml`
  - `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `cloud/task_084_crm_hang_root_cause/deploy_controller.py` ← 2 workflows
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_084_crm_hang_root_cause/evidence/deploy.js` ← 2 workflows
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_084_crm_hang_root_cause/remote_installer.py` ← 2 workflows
  - `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
  - `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `cloud/task_085_stage_payload_reset/controller.py` ← 2 workflows
  - `.github/workflows/owner_ua0011_korea_now_production.yml`
  - `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `cloud/task_085_stage_payload_reset/evidence/production.js` ← 2 workflows
  - `.github/workflows/owner_ua0011_korea_now_production.yml`
  - `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `cloud/task_085_stage_payload_reset/remote_installer.py` ← 2 workflows
  - `.github/workflows/owner_ua0011_korea_now_production.yml`
  - `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `cloud/task_085_stage_payload_reset/stage_payload_guard.py` ← 2 workflows
  - `.github/workflows/owner_ua0011_korea_now_production.yml`
  - `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `cloud/task_085_stage_payload_reset/tests/test_remote_installer.py` ← 2 workflows
  - `.github/workflows/owner_ua0011_korea_now_production.yml`
  - `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `cloud/task_085_stage_payload_reset/tests/test_stage_payload_guard.py` ← 2 workflows
  - `.github/workflows/owner_ua0011_korea_now_production.yml`
  - `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `cloud/task_088_ua0011_korea/evidence/full_card_gate_a.js` ← 2 workflows
  - `.github/workflows/owner_ua0011_full_card_gate_a.yml`
  - `.github/workflows/task086_renderer_gate_a.yml`
- `cloud/task_096_tech_spec_ai_crm/data_enrichment/recovery10_status.js` ← 2 workflows
  - `.github/workflows/task096_final_fix.yml`
  - `.github/workflows/task096_recovery10.yml`
- `cloud/task_096_tech_spec_ai_crm/data_enrichment/remote_apply.py` ← 2 workflows
  - `.github/workflows/task096_data_enrichment_sandbox.yml`
  - `.github/workflows/task096_enrichment_repair_v8.yml`
- `cloud/task_098_editorial_atlas_qa/live_site_probe.js` ← 2 workflows
  - `.github/workflows/task098_editorial_atlas_qa.yml`
  - `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- `cloud/task_098_editorial_atlas_qa/redirect_probe.js` ← 2 workflows
  - `.github/workflows/task098_editorial_atlas_qa.yml`
  - `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- `cloud/task_098_editorial_atlas_qa/source_probe_qa_machine.js` ← 2 workflows
  - `.github/workflows/task098_editorial_atlas_qa.yml`
  - `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- `cloud/task_099_site_crm_repair/evidence/production_gate.js` ← 2 workflows
  - `.github/workflows/task099_partial_recovery.yml`
  - `.github/workflows/task099_site_crm_production.yml`
- `cloud/task_099_site_crm_repair/evidence/visual_evidence.js` ← 2 workflows
  - `.github/workflows/task099_partial_recovery.yml`
  - `.github/workflows/task099_site_crm_production.yml`
- `cloud/task_099_site_crm_repair/task099_finalize.py` ← 2 workflows
  - `.github/workflows/task099_partial_recovery.yml`
  - `.github/workflows/task099_site_crm_production.yml`
- `cloud/task_099_site_crm_repair/task099_visual.py` ← 2 workflows
  - `.github/workflows/task099_partial_recovery.yml`
  - `.github/workflows/task099_site_crm_production.yml`

## Workflow-to-workflow edges

- `.github/workflows/ferry_wording_gate_a.yml` → `.github/workflows/ferry_wording_gate_a.yml`
- `.github/workflows/ferry_wording_gate_b.yml` → `.github/workflows/ferry_wording_gate_b.yml`
- `.github/workflows/owner_ua0011_full_card_gate_a.yml` → `.github/workflows/owner_ua0011_full_card_gate_a.yml`
- `.github/workflows/owner_ua0011_korea_now_production.yml` → `.github/workflows/owner_ua0011_korea_now_production.yml`
- `.github/workflows/owner_ua0011_korea_slim_production.yml` → `.github/workflows/owner_ua0011_korea_slim_production.yml`
- `.github/workflows/pythonanywhere_sync.yml` → `.github/workflows/pythonanywhere_sync.yml`
- `.github/workflows/safe_workflow_watchdog.yml` → `.github/workflows/safe_workflow_watchdog.yml`
- `.github/workflows/seo-rehab-068-production.yml` → `.github/workflows/seo-rehab-068-production.yml`
- `.github/workflows/seo-watch-smoke.yml` → `.github/workflows/seo-watch-smoke.yml`
- `.github/workflows/task037_discovery.yml` → `.github/workflows/task037_discovery.yml`
- `.github/workflows/task039_retry.yml` → `.github/workflows/task039_retry.yml`
- `.github/workflows/task039_safe_inbox_sync.yml` → `.github/workflows/task039_safe_inbox_sync.yml`
- `.github/workflows/task049_gate_a.yml` → `.github/workflows/task049_gate_a.yml`
- `.github/workflows/task049_gate_b.yml` → `.github/workflows/task049_gate_b.yml`
- `.github/workflows/task049_gate_b_preflight.yml` → `.github/workflows/task049_gate_b_preflight.yml`
- `.github/workflows/task060_install_token_free_ocr.yml` → `.github/workflows/task060_install_token_free_ocr.yml`
- `.github/workflows/task060_read_live_context.yml` → `.github/workflows/task060_read_live_context.yml`
- `.github/workflows/task060_runtime_capabilities.yml` → `.github/workflows/task060_runtime_capabilities.yml`
- `.github/workflows/task061_crm_ai_card.yml` → `.github/workflows/task061_crm_ai_card.yml`
- `.github/workflows/task062_crm_voice.yml` → `.github/workflows/task062_crm_voice.yml`
- `.github/workflows/task062_read_voice_context.yml` → `.github/workflows/task062_read_voice_context.yml`
- `.github/workflows/task064_crm_db_lock_hotfix.yml` → `.github/workflows/task064_crm_db_lock_hotfix.yml`
- `.github/workflows/task064_diagnostics_permanent.yml` → `.github/workflows/task064_diagnostics_permanent.yml`
- `.github/workflows/task064_emergency_crm_quiesce.yml` → `.github/workflows/task064_emergency_crm_quiesce.yml`
- `.github/workflows/task064_read_crm_lock_context.yml` → `.github/workflows/task064_read_crm_lock_context.yml`
- `.github/workflows/task064_trace_wrapper_probe.yml` → `.github/workflows/task064_trace_wrapper_probe.yml`
- `.github/workflows/task065_counter_v2_hotfix.yml` → `.github/workflows/task065_counter_v2_hotfix.yml`
- `.github/workflows/task065_crm_photo_fastpath.yml` → `.github/workflows/task065_crm_photo_fastpath.yml`
- `.github/workflows/task065_photo_path_probe.yml` → `.github/workflows/task065_photo_path_probe.yml`
- `.github/workflows/task065_ua0011_probe.yml` → `.github/workflows/task065_ua0011_probe.yml`
- `.github/workflows/task065_voice_path_probe.yml` → `.github/workflows/task065_voice_path_probe.yml`
- `.github/workflows/task066_stage_anchor_deploy.yml` → `.github/workflows/task066_stage_anchor_deploy.yml`
- `.github/workflows/task066_stage_anchor_probe.yml` → `.github/workflows/task066_stage_anchor_probe.yml`
- `.github/workflows/task067_crm_online_guard_deploy.yml` → `.github/workflows/task067_crm_online_guard_deploy.yml`
- `.github/workflows/task067_health_probe.yml` → `.github/workflows/task067_health_probe.yml`
- `.github/workflows/task067_read_only_audit.yml` → `.github/workflows/task067_read_only_audit.yml`
- `.github/workflows/task068_catalog_structure_probe.yml` → `.github/workflows/task068_catalog_structure_probe.yml`
- `.github/workflows/task068_ferry_vin_deploy.yml` → `.github/workflows/task068_ferry_vin_deploy.yml`
- `.github/workflows/task068_ferry_vin_probe.yml` → `.github/workflows/task068_ferry_vin_probe.yml`
- `.github/workflows/task069_crm_container_gate_a.yml` → `.github/workflows/task069_crm_container_gate_a.yml`
- `.github/workflows/task069_crm_container_gate_b.yml` → `.github/workflows/task069_crm_container_gate_b.yml`
- `.github/workflows/task069_crm_container_readonly.yml` → `.github/workflows/task069_crm_container_readonly.yml`
- `.github/workflows/task070_real_context_probe.yml` → `.github/workflows/task070_real_context_probe.yml`
- `.github/workflows/task071_call_path_read.yml` → `.github/workflows/task071_call_path_read.yml`
- `.github/workflows/task072_gate_a_v2.yml` → `.github/workflows/task072_gate_a_v2.yml`
- `.github/workflows/task072_gate_a_v2.yml` → `.github/workflows/task072_gate_b.yml`
- `.github/workflows/task073_gate_a_live_probe.yml` → `.github/workflows/task073_gate_a_live_probe.yml`
- `.github/workflows/task073_gate_a_v5.yml` → `.github/workflows/task073_gate_a_v5.yml`
- `.github/workflows/task074_catalog_card_unify.yml` → `.github/workflows/task074_catalog_card_unify.yml`
- `.github/workflows/task075_stage_guard_sandbox.yml` → `.github/workflows/task075_stage_guard_sandbox.yml`
- `.github/workflows/task076_eta_gate_a_live.yml` → `.github/workflows/task076_eta_gate_a_live.yml`
- `.github/workflows/task077_container_stage_sync_gate_a.yml` → `.github/workflows/task077_container_stage_sync_gate_a.yml`
- `.github/workflows/task078_voice_watchdog_gate_a.yml` → `.github/workflows/task078_voice_watchdog_gate_a.yml`
- `.github/workflows/task080_price_candidate.yml` → `.github/workflows/task080_price_candidate.yml`
- `.github/workflows/task080_price_gate_a.yml` → `.github/workflows/task080_price_gate_a.yml`
- `.github/workflows/task081_publish_repair_gate_a_v2.yml` → `.github/workflows/task081_publish_repair_gate_a_v2.yml`
- `.github/workflows/task081_publish_repair_live_audit_v2.yml` → `.github/workflows/task081_publish_repair_live_audit_v2.yml`
- `.github/workflows/task082_audit_probe.yml` → `.github/workflows/task082_audit_probe.yml`
- `.github/workflows/task082_audit_probe_persist.yml` → `.github/workflows/task082_audit_probe_persist.yml`
- `.github/workflows/task082_live_source_probe.yml` → `.github/workflows/task082_live_source_probe.yml`
- `.github/workflows/task082_source_probe_persist.yml` → `.github/workflows/task082_source_probe_persist.yml`
- `.github/workflows/task082_stage_probe.yml` → `.github/workflows/task082_stage_probe.yml`
- `.github/workflows/task082_vin4_title_deploy.yml` → `.github/workflows/task082_vin4_title_deploy.yml`
- `.github/workflows/task082_vin4_title_production.yml` → `.github/workflows/task082_vin4_title_production.yml`
- `.github/workflows/task083_catalog_dedup.yml` → `.github/workflows/task083_catalog_dedup.yml`
- `.github/workflows/task083_production_hold.yml` → `.github/workflows/task083_production_hold.yml`
- `.github/workflows/task083_publish_transaction.yml` → `.github/workflows/task083_publish_transaction.yml`
- `.github/workflows/task084_crm_hang_remediation_gate_a.yml` → `.github/workflows/task084_crm_hang_remediation_gate_a.yml`
- `.github/workflows/task084_crm_hang_root_cause.yml` → `.github/workflows/task084_crm_hang_root_cause.yml`
- `.github/workflows/task084_crm_hang_root_cause_production.yml` → `.github/workflows/task084_crm_hang_root_cause_production.yml`
- `.github/workflows/task084_gate_a_live_read_only.yml` → `.github/workflows/task084_gate_a_live_read_only.yml`
- `.github/workflows/task084_korea_reset_gate_a.yml` → `.github/workflows/task084_korea_reset_gate_a.yml`
- `.github/workflows/task086_public_catalog_readonly_probe.yml` → `.github/workflows/task086_public_catalog_readonly_probe.yml`
- `.github/workflows/task086_renderer_gate_a.yml` → `.github/workflows/task086_renderer_gate_a.yml`
- `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml` → `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
- `.github/workflows/task089_crm_voice_photo_live_audit.yml` → `.github/workflows/task089_crm_voice_photo_live_audit.yml`
- `.github/workflows/task090_catalog_design_restore.yml` → `.github/workflows/task090_catalog_design_restore.yml`
- `.github/workflows/task091_numeric_claim_guard.yml` → `.github/workflows/task091_numeric_claim_guard.yml`
- `.github/workflows/task092_launch_after_limit.yml` → `.github/workflows/task092_launch_after_limit.yml`
- `.github/workflows/task093_home_stage_counter_sync_production.yml` → `.github/workflows/task093_home_stage_counter_sync_production.yml`
- `.github/workflows/task095_catalog_visual_diagnostic.yml` → `.github/workflows/task095_catalog_visual_diagnostic.yml`
- `.github/workflows/task095_catalog_visual_repair.yml` → `.github/workflows/task095_catalog_visual_repair.yml`
- `.github/workflows/task095_catalog_visual_repair_v2.yml` → `.github/workflows/task095_catalog_visual_repair_v2.yml`
- `.github/workflows/task095_catalog_visual_repair_v3.yml` → `.github/workflows/task095_catalog_visual_repair_v3.yml`
- `.github/workflows/task096_autorun_orchestrator.yml` → `.github/workflows/task096_autorun_orchestrator.yml`
- `.github/workflows/task096_claude_sandbox.yml` → `.github/workflows/task096_claude_sandbox.yml`
- `.github/workflows/task096_controller_sandbox.yml` → `.github/workflows/task096_controller_sandbox.yml`
- `.github/workflows/task096_data_enrichment_sandbox.yml` → `.github/workflows/task096_data_enrichment_sandbox.yml`
- `.github/workflows/task096_enrichment_repair_v2.yml` → `.github/workflows/task096_enrichment_repair_v2.yml`
- `.github/workflows/task096_enrichment_repair_v3.yml` → `.github/workflows/task096_enrichment_repair_v3.yml`
- `.github/workflows/task096_enrichment_repair_v4.yml` → `.github/workflows/task096_enrichment_repair_v4.yml`
- `.github/workflows/task096_enrichment_repair_v5.yml` → `.github/workflows/task096_enrichment_repair_v5.yml`
- `.github/workflows/task096_enrichment_repair_v6.yml` → `.github/workflows/task096_enrichment_repair_v6.yml`
- `.github/workflows/task096_enrichment_repair_v7.yml` → `.github/workflows/task096_enrichment_repair_v7.yml`
- `.github/workflows/task096_enrichment_repair_v8.yml` → `.github/workflows/task096_enrichment_repair_v8.yml`
- `.github/workflows/task096_recovery10.yml` → `.github/workflows/task096_recovery10.yml`
- `.github/workflows/task097_editorial_atlas_audit.yml` → `.github/workflows/claude_autopilot.yml`
- `.github/workflows/task097_editorial_atlas_audit.yml` → `.github/workflows/task097_editorial_atlas_audit.yml`
- `.github/workflows/task098_editorial_atlas_qa.yml` → `.github/workflows/task098_editorial_atlas_qa.yml`
- `.github/workflows/task098_editorial_atlas_qa_retry.yml` → `.github/workflows/task098_editorial_atlas_qa_retry.yml`
- `.github/workflows/task099_live_audit.yml` → `.github/workflows/task099_live_audit.yml`
- `.github/workflows/task099_partial_recovery.yml` → `.github/workflows/task099_partial_recovery.yml`
- `.github/workflows/task099_remote_state_probe.yml` → `.github/workflows/task099_remote_state_probe.yml`
- `.github/workflows/task099_site_crm_production.yml` → `.github/workflows/task099_site_crm_production.yml`
- `.github/workflows/task100_home_live_sync.yml` → `.github/workflows/task100_home_live_sync.yml`
- `.github/workflows/task102_seo_audit.yml` → `.github/workflows/task102_seo_audit.yml`
- `.github/workflows/task102_seo_routing_probe.yml` → `.github/workflows/task102_seo_routing_probe.yml`
- `.github/workflows/task104_integration_canary.yml` → `.github/workflows/task104_integration_canary.yml`
- `.github/workflows/task104_self_recovery_sandbox.yml` → `.github/workflows/task104_self_recovery_sandbox.yml`
- `.github/workflows/task105_phase0_audit.yml` → `.github/workflows/task105_phase0_audit.yml`
- `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml` → `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml`

## Concurrency groups

### `ua-art-production-writer` (9)
- `.github/workflows/task077_container_stage_sync_gate_b.yml`
- `.github/workflows/task086_ua0011_ferry_stage_counter_production.yml`
- `.github/workflows/task090_catalog_design_restore.yml`
- `.github/workflows/task091_numeric_claim_guard.yml`
- `.github/workflows/task093_home_stage_counter_sync_production.yml`
- `.github/workflows/task095_catalog_visual_repair.yml`
- `.github/workflows/task095_catalog_visual_repair_v2.yml`
- `.github/workflows/task095_catalog_visual_repair_v3.yml`
- `.github/workflows/task100_home_live_sync.yml`

### `task096-autorun` (7)
- `.github/workflows/task096_enrichment_repair_v2.yml`
- `.github/workflows/task096_enrichment_repair_v3.yml`
- `.github/workflows/task096_enrichment_repair_v4.yml`
- `.github/workflows/task096_enrichment_repair_v5.yml`
- `.github/workflows/task096_enrichment_repair_v6.yml`
- `.github/workflows/task096_enrichment_repair_v7.yml`
- `.github/workflows/task096_enrichment_repair_v8.yml`

### `claude-autopilot` (3)
- `.github/workflows/claude_autopilot.yml`
- `.github/workflows/task094_claude_autostart.yml`
- `.github/workflows/task103_ge_8country_sandbox_autostart.yml`

### `task064-crm-db-lock` (3)
- `.github/workflows/task064_crm_db_lock_hotfix.yml`
- `.github/workflows/task064_emergency_crm_quiesce.yml`
- `.github/workflows/task064_read_crm_lock_context.yml`

### `ua-art-production-crm` (3)
- `.github/workflows/task073_gate_b_v5.yml`
- `.github/workflows/task081_publish_repair_gate_b_v2.yml`
- `.github/workflows/task082_vin4_title_production.yml`

### `task096-data-enrichment-sandbox` (2)
- `.github/workflows/task096_data_enrichment_sandbox.yml`
- `.github/workflows/task096_recovery10.yml`

### `task098-editorial-atlas-qa` (2)
- `.github/workflows/task098_editorial_atlas_qa.yml`
- `.github/workflows/task098_editorial_atlas_qa_retry.yml`

### `task099-site-crm-production` (2)
- `.github/workflows/task099_partial_recovery.yml`
- `.github/workflows/task099_site_crm_production.yml`

### `ferry-wording-isolated-gate-a` (1)
- `.github/workflows/ferry_wording_gate_a.yml`

### `ferry-wording-task-063-approved-gate-b` (1)
- `.github/workflows/ferry_wording_gate_b.yml`

### `overnight-autopilot-production-dispatch` (1)
- `.github/workflows/overnight_autopilot_production_dispatch.yml`

### `overnight-task099-transient-recovery` (1)
- `.github/workflows/overnight_task099_transient_recovery.yml`

### `owner-ua0011-korea-now-20260829` (1)
- `.github/workflows/owner_ua0011_korea_now_production.yml`

### `owner-ua0011-korea-slim-20260829` (1)
- `.github/workflows/owner_ua0011_korea_slim_production.yml`

### `pythonanywhere-inbox-sync` (1)
- `.github/workflows/pythonanywhere_sync.yml`

### `safe-workflow-watchdog` (1)
- `.github/workflows/safe_workflow_watchdog.yml`

### `seo-rehab-guard-068-production` (1)
- `.github/workflows/seo-rehab-068-production.yml`

### `task-039-pinned-safe-retry` (1)
- `.github/workflows/task039_retry.yml`

### `task037-discovery-readonly` (1)
- `.github/workflows/task037_discovery.yml`

### `task039-safe-inbox-sync` (1)
- `.github/workflows/task039_safe_inbox_sync.yml`

### `task049-gate-b-readonly-preflight` (1)
- `.github/workflows/task049_gate_b_preflight.yml`

### `task049-logistics-hub-gate-a` (1)
- `.github/workflows/task049_gate_a.yml`

### `task049-logistics-hub-gate-b` (1)
- `.github/workflows/task049_gate_b.yml`

### `task058-crm-ocr-readonly` (1)
- `.github/workflows/task058_crm_ocr_readonly.yml`

### `task059-ai-fast-schema` (1)
- `.github/workflows/task059_ai_fast_schema.yml`

### `task060-install-token-free-ocr` (1)
- `.github/workflows/task060_install_token_free_ocr.yml`

### `task060-read-live-context` (1)
- `.github/workflows/task060_read_live_context.yml`

### `task060-runtime-capabilities` (1)
- `.github/workflows/task060_runtime_capabilities.yml`

### `task061-crm-ai-card` (1)
- `.github/workflows/task061_crm_ai_card.yml`

### `task062-crm-voice` (1)
- `.github/workflows/task062_crm_voice.yml`

### `task062-read-voice-context` (1)
- `.github/workflows/task062_read_voice_context.yml`

### `task064-permanent-diagnostics-repair` (1)
- `.github/workflows/task064_diagnostics_permanent.yml`

### `task065-crm-photo-fastpath` (1)
- `.github/workflows/task065_crm_photo_fastpath.yml`

### `task065-crm-rehabilitation-v2` (1)
- `.github/workflows/task065_counter_v2_hotfix.yml`

### `task066-stage-anchor-probe` (1)
- `.github/workflows/task066_stage_anchor_probe.yml`

### `task066-stage-anchor-v1-1-deploy` (1)
- `.github/workflows/task066_stage_anchor_deploy.yml`

### `task067-crm-online-guard-read-only-audit` (1)
- `.github/workflows/task067_read_only_audit.yml`

### `task067-crm-online-guard-v1-3-deploy` (1)
- `.github/workflows/task067_crm_online_guard_deploy.yml`

### `task068-ferry-vin-probe` (1)
- `.github/workflows/task068_ferry_vin_probe.yml`

### `task068-ferry-vin-v1-1-deploy` (1)
- `.github/workflows/task068_ferry_vin_deploy.yml`

### `task069-crm-container-gate-a` (1)
- `.github/workflows/task069_crm_container_gate_a.yml`

### `task069-crm-container-production-gate-b` (1)
- `.github/workflows/task069_crm_container_gate_b.yml`

### `task069-crm-container-readonly-audit` (1)
- `.github/workflows/task069_crm_container_readonly.yml`

### `task070-real-crm-context-read` (1)
- `.github/workflows/task070_real_context_probe.yml`

### `task071-current-crm-call-path-read` (1)
- `.github/workflows/task071_call_path_read.yml`

### `task072-description-production-gate-b` (1)
- `.github/workflows/task072_gate_b.yml`

### `task072-gate-a-v2` (1)
- `.github/workflows/task072_gate_a_v2.yml`

### `task073-live-readonly-gate-a-probe` (1)
- `.github/workflows/task073_gate_a_live_probe.yml`

### `task075-sandbox-canary` (1)
- `.github/workflows/task075_stage_guard_sandbox.yml`

### `task076-eta-gate-a-live` (1)
- `.github/workflows/task076_eta_gate_a_live.yml`

### `task077-container-stage-sync-gate-a` (1)
- `.github/workflows/task077_container_stage_sync_gate_a.yml`

### `task078-voice-watchdog-gate-a` (1)
- `.github/workflows/task078_voice_watchdog_gate_a.yml`

### `task080-price-candidate` (1)
- `.github/workflows/task080_price_candidate.yml`

### `task080-price-recognition-gate-a` (1)
- `.github/workflows/task080_price_gate_a.yml`

### `task081-publish-repair-gate-a-v3` (1)
- `.github/workflows/task081_publish_repair_gate_a_v2.yml`

### `task081-publish-repair-live-audit-v2` (1)
- `.github/workflows/task081_publish_repair_live_audit_v2.yml`

### `task082-audit-probe` (1)
- `.github/workflows/task082_audit_probe.yml`

### `task082-stage-probe` (1)
- `.github/workflows/task082_stage_probe.yml`

### `task082-vin4-live-source-probe` (1)
- `.github/workflows/task082_live_source_probe.yml`

### `task082-vin4-title-production` (1)
- `.github/workflows/task082_vin4_title_deploy.yml`

### `task083-catalog-dedup-verification` (1)
- `.github/workflows/task083_catalog_dedup.yml`

### `task083-publish-transaction-production` (1)
- `.github/workflows/task083_publish_transaction.yml`

### `task084-crm-hang-remediation` (1)
- `.github/workflows/task084_crm_hang_root_cause_production.yml`

### `task084-crm-hang-remediation-gate-a` (1)
- `.github/workflows/task084_crm_hang_remediation_gate_a.yml`

### `task084-crm-hang-root-cause-live-audit` (1)
- `.github/workflows/task084_crm_hang_root_cause.yml`

### `task084-ua0011-korea-reset-gate-a` (1)
- `.github/workflows/task084_korea_reset_gate_a.yml`

### `task084-ua0011-read-only-gate-a` (1)
- `.github/workflows/task084_gate_a_live_read_only.yml`

### `task089-crm-voice-photo-live-audit` (1)
- `.github/workflows/task089_crm_voice_photo_live_audit.yml`

### `task092-claude-autopilot` (1)
- `.github/workflows/task092_launch_after_limit.yml`

### `task092-claude-autostart` (1)
- `.github/workflows/task092_anthropic_reset_autostart.yml`

### `task096-autorun-orchestrator` (1)
- `.github/workflows/task096_autorun_orchestrator.yml`

### `task096-claude-sandbox` (1)
- `.github/workflows/task096_claude_sandbox.yml`

### `task096-controller-sandbox` (1)
- `.github/workflows/task096_controller_sandbox.yml`

### `task097-editorial-atlas-audit` (1)
- `.github/workflows/task097_editorial_atlas_audit.yml`

### `task099-site-crm-completion` (1)
- `.github/workflows/task099_live_audit.yml`

### `task102-seo-readonly-audit` (1)
- `.github/workflows/task102_seo_audit.yml`

### `task104-canary-${{ inputs.cycle }}` (1)
- `.github/workflows/task104_canary_worker.yml`

### `task104-canary-recovery` (1)
- `.github/workflows/task104_canary_recovery.yml`

### `task104-integration-canary` (1)
- `.github/workflows/task104_integration_canary.yml`

### `task104-self-recovery-sandbox` (1)
- `.github/workflows/task104_self_recovery_sandbox.yml`

### `task105-phase0-audit` (1)
- `.github/workflows/task105_phase0_audit.yml`

### `ua-art-autopilot-core-v2-sandbox` (1)
- `.github/workflows/ua_art_autopilot_core_v2_sandbox.yml`

### `ua-art-production-write` (1)
- `.github/workflows/task074_catalog_card_unify.yml`

### `ua-art-task095-visual-diagnostic` (1)
- `.github/workflows/task095_catalog_visual_diagnostic.yml`

## Finding

Task-specific workflow names dominate the control plane. Shared behavior is implemented by
copying orchestration patterns rather than calling a small set of parameterized reusable workflows.
That increases transport drift, retry divergence and the probability that a repair fixes one path
but not its siblings.
