# CRM-hidden photos must stay out of public galleries

Owner request, 2026-09-27: remove the technical first photo from UA-0023 and prevent recurrence. Production installation and public removal are **not complete**.

Read-only diagnosis: the CRM already lists the technical photo in `hidden_photos`. The downloader ledger `.video_sinhron.json`, key `foto:UA-0023`, binds that identity to `001.jpg`. There are 38 source photos and one hidden identity. Both `stranica.kadry_mashiny` and `master_card.vybrat_glavnoe` select directory files without consulting this visibility field. `master_card.dannye` reads the complete CRM row, so the visibility metadata is available to the renderer.

The candidate changes only these two function bodies and adds `photo_visibility.py`, a standard-library helper. It maps filenames through the existing downloader ledger, filters all copies of hidden identities, and preserves the input order and original filenames. A hidden chosen cover falls back to the first visible photo. An all-hidden set cannot fall back to a hidden cover. Missing or malformed bindings stop rendering for cards with hidden photos. Cards with no hidden photos retain their current selection behaviour.

No CRM row changes, media deletion, filename renumbering, new OCR, new service, intake redesign or publication-queue reset is included. Technical originals remain available to CRM; the requested removal is from public display.

Validation:

```sh
python3 -B -m unittest discover -s cloud/crm_photo_visibility_001 -p 'test_*.py' -v
```

12 tests pass, covering the reported first-photo leak, hidden selected cover, all-hidden input, duplicate bindings for a hidden identity, malformed metadata, missing bindings, preserved order and unchanged archive. Tests demonstrate the original selection exposing the source and the candidate excluding it. The builder checks both exact source SHA256 values and AST-scopes each replacement to its named function; it compiles complete candidate modules without importing the live application.

Official Python references checked: [JSON decoding](https://docs.python.org/3.10/library/json.html), [path handling](https://docs.python.org/3.10/library/pathlib.html), and [atomic replacement](https://docs.python.org/3.10/library/os.html#os.replace). The helper is read-only; a later installer must use the existing backed-up atomic source lifecycle.

Current deployment blocker: main run `36308311986` belongs to the separate publisher-latency R4 task. Its controller failed with HTTP 500; its rollback failed with `REMOTE_ROLLBACK:TransportError:BOT_STATE_TIMEOUT`. At 09:32:39 UTC the control plane persisted `EMERGENCY_HALT`, with rollback reserved but not performed. This photo task did not start that run or modify its recovery state.

Continuation, after evidence-backed reconciliation of the existing transaction:

1. Refresh source hashes, CPU/storage and the UA-0023 row/ledger. Build this exact three-file candidate against the live files; review the complete diff and perform the normal private preview.
2. Prepare the exact backup/rollback manifest and production gates. Preserve all other source modules and all CRM rows. Install through main Actions only; keep source replacement and rollback under the existing writer locks.
3. Republish only UA-0023 through the existing transactional publisher, with explicit target-page/catalog/cover-derivative scope, backup, before/after protection of other cards, and public verification. Do not bypass the normal guard or post guessed future HTML hashes.
4. Verify the ordinary public card has 37 visible photos, excludes `001.jpg` and its derivatives everywhere in its gallery, and uses a visible car photo as its cover. Confirm both catalogs reflect the same selection and source originals/CRM metadata remain intact.

Do not claim this patch is installed or the technical photo has disappeared until those checks pass. No launch marker or delayed deployment is created by this candidate.
