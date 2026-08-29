# UA-0011-STAGE-PAYLOAD-RESET-005 v1.0

STATUS: **ROLLED_BACK**

- UA-0011 status: `—`
- Container removed: PASS
- ETA/days removed: PASS
- Permanent stage payload guard: NOT VERIFIED
- Immediate + delayed public checks: NOT VERIFIED
- Bot restart: PASS
- Runtime LLM tokens: 0
- Rollback: {"backup_root": "/home/Carix/autopilot_inbox/cloud/task_083_catalog_dedup/task085_backups/20260829T091709Z_272639a8cc", "contract_id": "UA-0011-STAGE-PAYLOAD-RESET-005-V1.0", "errors": [], "finished_at_utc": "2026-08-29T09:17:13Z", "mode": "ROLLBACK", "production_write": true, "quick_check": "ok", "reason": "automatic_apply_failure", "runtime_llm_tokens": 0, "started_at_utc": "2026-08-29T09:17:13Z", "status": "PASS", "target": {"auto_number": "UA-0011", "days_to_kyiv": null, "eta_manual": "2026-09-28", "ge_arrived": null, "ge_port": null, "ge_released": null, "ge_to_kyiv_at": null, "id": 18, "published": 1, "sea_container": "ONEYSELGB4471700", "sea_date_out": null, "sea_port_from": null, "status": "sea_loaded", "updated_at": "2026-08-29T08:28:32", "vin": "KMHE341DBKA544289"}}
- Errors: ControllerError:APPLY_FAIL:Task085Error:PUBLISHER_FAILED:Публикация отменена при записи (PUBLICATION BLOCKED UA-0011: пропал раздел «Комплексная диагностика»). Выполнен откат.
