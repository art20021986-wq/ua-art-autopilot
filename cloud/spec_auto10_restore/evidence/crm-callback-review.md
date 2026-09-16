# CRM callback repair: independent review

Date: 2026-09-09. Verdict: **PASS for the isolated cancellation repair and the stated callback scenarios.** No must-fix runtime regression was found in this narrow diff. This review does not close Gate B or authorize production execution.

The frozen `cars_ui.py` leaves `ua099_spec_edit` active when the operator cancels a specification edit and starts editing a normal CRM field. The registered text consumer in group `-3` then consumes the next message before `catch_message` in group `-1`. The original result reproduces the concrete corruption: `2018` replaces the specification value `4855`, while the CRM year remains `2017`.

The pure patch adds five state-cleanup statements across `drop_wait`, `edit_ask`, the two historical specification-screen definitions and the specification editor. The active screen resolves to the later definition at registration time. Existing staff checks, actor checks, card/specification binding and persistence functions remain unchanged. Independently applying the patch produced the declared output hash; modified and already-patched inputs were rejected. No application module was imported during that check.

The patched result preserves specification value `4855` and changes the CRM year to `2018`. It also exercises cancellation by opening another card or another field editor, a legitimate manual specification edit, the actual scanner and one actual publication-sync operation, hiding, republishing, required-field rejection and deletion. The two generated page roots retain one visible VIN, the specification and the pinned static-asset fingerprint. Original specification facts survive deletion.

The harness preserves actual registered callback references and invokes the actual SQLite and publication functions. Telegram objects, media presentation, unused AI imports and dispatch mechanics are substitutes. Worker registration is observed through a replaced `start_worker`; no background worker or its timing runs. The sync scenario explicitly invokes `scan_new_vins` and `sync_one`, and uses a local generated-page reader instead of public HTTP. The report discloses these limits and leaves production and Gate B unverified. Zero IO-guard counters describe this trusted-code isolated run, not an operating-system sandbox or proof of production writer exclusion.

Wording boundary: “all cancellation paths” in the scenario label should be read only as the three exercised routes: Cancel to the specification list, card navigation, and opening a normal field editor. The result does not enumerate every callback in the CRM.

Reviewed identities:

| Item | SHA-256 |
|---|---|
| Pure patcher | `97e1f170301d26403e115962392587f141be40a97b94acae412e3caeec8611f1` |
| Harness at review | `a5a34c6b67c9315b05d924ded90762a02f344c246c74a1bf65068e912d5fbcf6` |
| Frozen source | `32dfec40ca2e6badfab222fd811fa710c52708fc0ff6bad80cbce79c0df5a0ec` |
| Patched source | `57ad5acc340d412aa9d95e1ef56c7de85d4346ad6bbc755fda311763f3637a42` |
| Original result (`v2-original-03`) | `cb453b7dbc5fb5be0c78131c9b9282cae027a6f72bf4faf75aff3c99118549a5` |
| Patched result (`v3-patched-02`) | `7eda47b98ddcaee567d348ce3ab47c0768b8e245a71247de67b5100235bc9f22` |

Review method: bounded source inspection, evidence inspection, independent pure diff and pin-rejection checks. No repeated integration suite, live chat, production access or production mutation.
