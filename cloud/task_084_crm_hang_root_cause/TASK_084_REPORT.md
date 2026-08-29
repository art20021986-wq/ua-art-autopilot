# CRM-HANG-ROOT-CAUSE-084 v1.0

STATUS: **FAIL**

- First bad source: task067 fixed 4.65-second deadline with a non-killable thread
- Killable process-group STT for both CRM voice paths: NOT VERIFIED
- Menu replay debounce: NOT VERIFIED
- Startup singleton and notice debounce: NOT VERIFIED
- CRM DB/media writes: NO
- One controlled restart: YES
- Backup: `/home/Carix/backups/task_084/20260829T085009Z`
- Immediate and delayed live checks: FAIL
- Errors: ControllerError:POSTCHECK_FAILED:InstallError:START_SINGLETON_NOT_HELD
