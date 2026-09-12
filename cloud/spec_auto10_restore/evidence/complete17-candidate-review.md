# Independent review: complete17 candidate assembly

Date: 2026-09-09. Result: **PASS for offline assembly only**. Reviewed the assembler, eight targeted test cases, pinned pure helper/patcher interfaces and the supplied final evidence. No additional tests, application imports, server operations or production writes were performed by this review.

| Binding | SHA-256 |
| --- | --- |
| complete17_candidate.py | ea0265bee0fc3b19fe5df6096dfb7f0676cce07a405bcaf34abfd26050ebdc24 |
| tests/test_complete17_candidate.py | de6211e9436f5af0abf26875cfd8f36ee11fccac118069505122e54205595395 |
| Candidate manifest | d800e55813b6edc24322f7021e924dd0052915f07414b42bd02f0a7c234522f5 |
| Final result receipt | 0c1c4c2277cd9cf752829e57bb39524571f0c82942c09367bf0cbb14e6b3ef8a |
| Test log | ac934d9801a90717782b54fcb2179d87b0634f6e5e85720f184bd0084f32184f |

The assembly retains the exact fifteen inherited module bytes and adds only pinned analytics and TASK083 writer patches. TASK083 retains its complete relative deployment path, `autopilot_inbox/cloud/task_083_catalog_dedup/installer.py`; a flattened installer is rejected. Sources, pure patchers and the base verifier are hash pinned; the assembler executes captured helper bytes and compiles candidate application bytes without importing them. The input set is checked again before and after readiness publication.

The destination must be new and disjoint from inputs. Root and nested writes use directory descriptors, `O_EXCL`, `O_NOFOLLOW`, regular-file checks and exact expected file sets. Existing output, symbolic links, source/helper drift, extra or flattened paths and altered manifest claims are rejected. The inherited final15 files and metadata remain unchanged in the supplied evidence.

Review found and resolved a readiness failure gap: final manifest writes and filesystem flushes originally fell outside cleanup. They now share the invalidation scope with final verification. The marker inode is recorded immediately after exclusive creation; cleanup uses the owned directory descriptor and unlinks only that exact marker, without first depending on the possibly replaced output pathname. The added test injects a real manifest `fsync` exception and requires that no ready manifest remains. The final supplied log records eight tests, zero failures/errors/skips.

This candidate is **not an installer**. Its manifest explicitly records `combined17_execution: NOT_RUN`, `overall_gate_b: NOT_EVALUATED` and `production_changed: false`; changing those claims makes verification fail. The inherited fifteen-module server result is a provenance reference, not proof that the two added writers have executed together with that runtime. Combined17 execution, writer drain/fencing, worker and source checks, controlled installation, service readback and actual publication remain separate gates. This review authorizes no HALT change or production action.
