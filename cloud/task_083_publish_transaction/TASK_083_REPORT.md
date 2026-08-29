# UA-0012/UA-0013 publication transaction repair

STATUS: **FAIL**

- UA-0012: stage 2 / more / На пароме
- UA-0013: stage 2 / more / На пароме
- Primary + diagnostic + both catalogs transaction: FAIL
- CRM bot false-success path replaced: ROLLED BACK
- Future publication rollback and exact single-message result: NOT INSTALLED
- CRM rows changed by deployment: NO
- Runtime LLM tokens: 0
- Code backup: ``
- Publication backup: ``
- Errors: ControllerError:INSTALL_FAILED:InstallError:INSTALL_ROLLED_BACK:{"transaction": {"backup_root": "/home/Carix/rezerv_publikacii/TASK083/20260829T091110Z-1bce44a7ae72", "removed": [], "restored": []}, "code": {"backup_root": "/home/Carix/autopilot_inbox/cloud/task_083_publish_transaction/backups/20260829T091110Z-8c49b4be00c1", "changed_paths": ["/home/Carix/publikaciya.py", "/home/Carix/cars_ui.py", "/home/Carix/publish_transaction_guard.py", "/home/Carix/catalog_stage_guard_core.py"]}}
