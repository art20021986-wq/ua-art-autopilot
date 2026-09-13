# Final17 v3: independent composition review

Date: 2026-09-09. Verdict: **PASS for the frozen byte composition and its evidence bindings.** No remaining must-fix issue was found in this bounded review. Overall Gate B remains `NOT_EVALUATED`.

The output contains exactly the 17 declared module files plus `manifest.json`. Independent byte comparison against frozen v2 confirms that only `cars_ui.py` changes; the other 16 modules are identical. Every module matches its declared output hash, and the recomputed file-closure digest matches the manifest. The UI output and patcher hashes match the repaired callback server receipt.

Two previously identified assembler issues were corrected before this freeze: public entry points normalize `..` with `os.path.abspath` before overlap checks, and final verification repeats the exact file-set check after byte and input-identity checks. Symlinks remain rejected. The manifest is written last into an exclusive new output; failure cleanup uses the held original directory descriptor and removes only the manifest inode owned by this assembly. Historical candidates and helpers remain unchanged.

The four recorded composition tests pass. They cover exact one-module composition and input preservation, changed/missing/extra module refusal, altered receipt refusal, existing-output preservation, symlink refusal and normalized-path overlap refusal. The expected symlink rejection emits a `ResourceWarning` from the preserved historical helper's scandir iterator. It does not turn that rejection into acceptance or invalidate the recorded test result. This review inspected the log and did not rerun the suite.

Both manifest evidence pairs match the saved reports and summaries byte for byte. The historical combined-v2 receipt and the repaired callback receipt are explicitly separate scopes. The callback summary records Python 3.10.12, completion at `2026-09-09T11:50:56.475287+00:00`, 28 watched files unchanged, no production changes and zero runtime IO-guard counters. Its repaired result binds the exact replacement UI bytes and reports `PASS`; the original run is explicitly identified as `KNOWN_UI_BUG_REPRODUCED`. The new manifest does not relabel the historical combined run as a fresh full-v3 execution.

Remaining limits are correctly retained: Telegram transport and dispatcher, external registrar modules, background-worker startup and timing, live ten-source collection, writer drain and handoff, installation, UA-0017/UA-0018 publication and real public read-back are not established by this composition. The callback synchronization scenario invokes the actual scanner and sync function directly with a local generated-page reader. Its PASS proves that scoped path, not public HTTP visibility or a running production worker.

Reviewed identities:

| Item | SHA-256 |
|---|---|
| Frozen v3 manifest | `14f42086fc8bc94aefc4e4c83bda50e01107c30d2ad893c00d658f60d0c64fff` |
| Pure v3 builder | `6b78ac67a6259cb8c49968fe16378203e6c1d15ef2eee63ef6a416c3d22500eb` |
| File closure | `b519021118fa849b1229dc861ffd9483caee2f2ae211061bcd56c5fe89a8a450` |
| Patched UI | `57ad5acc340d412aa9d95e1ef56c7de85d4346ad6bbc755fda311763f3637a42` |
| Repaired callback server report | `a5d9362d8b388fc16aefbebec92c4253b9c4ee1e02515bd5c9f51cb04e4615ca` |
| Callback server summary | `ca61f4a83936b236986272ca384d4e9b8c1722fe83eea63030a99de469a85ad4` |
| Four-test composition log | `d690aeae3f31655fda7a90019672ea1e5f1b7c5cb5e03af8148b46ddda32f374` |

Review method: source inspection, exact file-set and byte comparisons, recomputed digests, saved receipt inspection and recorded test-log inspection. No functional reruns, live service operations or production changes were performed.
