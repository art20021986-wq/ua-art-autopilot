# TASK105 — Temporary Workflow Retirement

The following task-specific migration workflows are retired before merge because their evidence has already passed and the permanent eight-workflow architecture is present:

- task105_phase0_audit.yml
- task105_fast_production_canary.yml
- task105_standard_canary.yml
- task105_standard_canary_recovery.yml
- task105_critical_adapter.yml
- task105_critical_adapter_v2.yml
- task105_phase6_acceptance.yml
- task105_phase6_acceptance_v2.yml

Their reports, receipts and root-cause evidence remain preserved under `cloud/task_105_fast_pipeline_*` and `state/receipts/`. No legacy production workflow outside TASK105 is deleted in this migration.
