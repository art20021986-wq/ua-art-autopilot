# Independent review: exact final17 v3 admission in handoff v4

Date: 2026-09-09 UTC. Review scope: source reads, hashes and diff only; no project execution, tests, edits, API or network calls by the reviewer.

Verdict: **No blocking issue found for the bounded local admission/install/rollback validation and BLOCKED readiness.** This does not establish production authority, prior-writer drain, a v4 server test or overall Gate B.

| Reviewed source | SHA-256 |
| --- | --- |
| `code_handoff_v4.py` | `0dec7fa5509da16b143698cee2a2ff5641385644c2f1ae01724fe516cce82000` |
| `verify_handoff_v4_candidate.py` | `90997dd8e7a2f9020b6884681923b0dbced1da204dddc475623b06e4a1d5c195` |
| `prepare_maintenance_v3.py` | `4516e6082390b4ec2c7c6593c55459b15b2027c6366b0175b5e8b146975db8ac` |

The final installer diff contains exactly the intended three literal edits: application manifest SHA, handoff schema and candidate label. All other installer bytes remain those of v3, whose historical server evidence is retained.

The harness hashes both complete candidate trees and project sources before project imports and admission, compares installer bytes after the three specified substitutions, and admits the actual final17 v3 pin without monkeypatching. It checks all 17 installed payloads and exact legacy hash/mode/mtime or absence on rollback. Required authority phases and each of the 17 install/rollback write phases are asserted. Network/process execution and production access guards precede project imports and candidate inspection. Fake authority, quota, session and legacy fixture data are explicitly labeled synthetic.

Fresh `CodeHandoff` instances read terminal receipts, matching the existing reviewed v3 test pattern. `handoff-v4-actual17-local-harness-attempt1.json` transparently records the first harness assertion failure caused by the existing in-memory `proof_digests` alias. That attempt completed fixture installation but not explicit rollback; its temporary fixture was cleaned. No algorithm change was hidden in the harness correction.

The final local result SHA is `16a89d5623f7043c7b118a6ceb5e19e350293963cb5334e5bcabbdc3b2486863`. Its current installer, harness, helper, application and dependency pins agree with the read files and readiness references.

Readiness is unconditionally `BLOCKED_BEFORE_EXACT_EXECUTION_PLAN`, with `observation_only=true`, `current_main_verified=false`, `execution_identity=UNASSIGNED`, `owner_command=null` and `overall_gate_b=NOT_EVALUATED`. The historical server v3 30-test evidence is SHA-pinned and expressly marked `NOT_A_V4_SERVER_RUN`; the actual17 v4 check is separately local and synthetic. The real upstream `verify_window`, complete prior-writer drain and exact owner-authorized execution plan remain prerequisites.
