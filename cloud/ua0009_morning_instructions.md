# UA-0009 — Morning Owner Instructions

1. **Upload/pull**: `cloud/ua0009_finish_runner.py` (single file, no deps).
2. **PythonAnywhere path**: place at `/home/Carix/ua0009_finish_runner.py`.
3. **Run**: open a Bash console on PythonAnywhere and run:
   `python3.10 /home/Carix/ua0009_finish_runner.py`
   (Do NOT run from the Web tab / do NOT reload the web app.)
4. **Duration**: under 1 minute (light, read-only job).
5. **Reports**:
   - `/home/Carix/video/ua0009_finish_report.txt`
   - `/home/Carix/video/ua0009_finish_report.json`
6. **Sandbox to inspect**:
   `/home/Carix/sandbox_ua0009_finish/video/ua0009_card_preview.html`
   (open in a private/incognito browser tab, do NOT link it from the live site)
7. **STOP if the report shows**: `STATUS: STOPPED`, or
   `SAFE_FOR_OWNER_VISUAL_REVIEW: NO`, or `DUPLICATE_CLASSIFICATION:
   TRUE_DUPLICATE`/`MORE_PROOF_NEEDED`, or `SQLITE_QUICK_CHECK: FAIL`, or
   `DATABASE_UNCHANGED: FAIL`, or `UA0001_0008_UNCHANGED: FAIL`.
   → Send the report file to ChatGPT/Claude; take no further action.
8. **Ready for your visual YES/NO if**: `STATUS: WAITING_VISUAL_CHECK` and
   `SAFE_FOR_OWNER_VISUAL_REVIEW: YES`. Open the sandbox card path above,
   check it looks correct, and reply YES or NO — nothing else.
9. **No production publish action is included in this run or these
   instructions.** Publication only happens after a separate explicit
   CRITICAL approval step (see `cloud/ua0009_publication_plan.md`).
