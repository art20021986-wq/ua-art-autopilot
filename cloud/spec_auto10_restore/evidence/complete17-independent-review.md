# Independent complete17 assembly review

Date: 2026-09-09.

Result: **PASS for offline assembly only**.

Reviewed `complete17_candidate.py` SHA-256:
`ea0265bee0fc3b19fe5df6096dfb7f0676cce07a405bcaf34abfd26050ebdc24`.

The reviewer independently ran all eight `test_complete17_candidate.py` tests against this final hash; all passed. These are the author's same eight cases, not eight additional unique tests.

The assembler requires the frozen final15 helper and manifest, verifies all inherited bytes, and applies the two exact-source/pinned-output writer patches. It retains TASK083's nested deployment path `autopilot_inbox/cloud/task_083_catalog_dedup/installer.py`. It compiles source bytes without importing candidate applications, creates an exclusive output directory and publishes the readiness manifest last. The manifest explicitly reports `combined17_execution=NOT_RUN` and `overall_gate_b=NOT_EVALUATED`.

Three additional bounded reviewer probes passed on the final code:

- A `../installer.py` input mapping was rejected with `EXACT_WRITER_MAPPING_REQUIRED` before output creation.
- Injecting an `autopilot_inbox` symlink during nested directory creation failed with `NotADirectoryError`; the outside directory remained empty and no readiness manifest existed.
- Renaming the owned output after writing its readiness marker, then replacing the visible output directory, caused assembly to fail. Cleanup used the retained directory descriptor and marker inode to remove only the owned marker from the moved directory. The replacement directory's owner sentinel remained untouched.

The final descriptor-based cleanup closes the directory-replacement gap identified during the concurrent reviews. No optional rework or broader testing is required for this assembly scope.

This result is not a combined17 runtime test, installer approval, live writer drain, WSGI reload, active-worker verification, source10 result or production publication receipt. No application data, live service, task schedule, HALT or queue was changed by this review.
