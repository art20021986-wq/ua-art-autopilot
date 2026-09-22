"""Historical chain and live-drift rejection; no server I/O or new authority."""
import copy
import hashlib
import json
from pathlib import Path
import unittest

import source_successor as S


class SourceSuccessorTests(unittest.TestCase):
    def setUp(self):
        self.raw = (Path(__file__).parent / S.SOURCE_SUCCESSOR_BINDING["file"]).read_bytes()
        self.chain = json.loads(self.raw)
        self.stage2 = json.loads(self.chain["artifacts"][S.STAGE2_PATH]["raw"])

    def semantic_mutation(self, path, fn):
        chain = copy.deepcopy(self.chain)
        value = json.loads(chain["artifacts"][path]["raw"])
        fn(value)
        raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
        chain["artifacts"][path] = {"raw": raw.decode(), "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
        return chain

    def test_exact_canonical_transition_accepted_without_receipt_mutation(self):
        before = copy.deepcopy(self.stage2)
        self.assertEqual(S.validate_source_successor(self.stage2, S.SUCCESSOR, self.raw), S.SOURCE_SUCCESSOR_BINDING)
        self.assertEqual(before, self.stage2)
        self.assertEqual(self.stage2["installed_source_sha256"], S.PREDECESSOR)

    def test_reencoded_or_tampered_chain_is_not_a_new_trust_root(self):
        for raw in (self.raw + b"\n", b"{}", json.dumps(self.chain).encode()):
            with self.subTest(raw_length=len(raw)), self.assertRaisesRegex(ValueError, "EXACT_REVIEWED_CHAIN"):
                S.validate_source_successor(self.stage2, S.SUCCESSOR, raw)

    def test_current_unknown_or_predecessor_source_rejected(self):
        for value in (S.PREDECESSOR, "0" * 64, None, "", S.SUCCESSOR.upper()):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "CURRENT_SOURCE_DRIFT"):
                S.validate_source_successor(self.stage2, value, self.raw)

    def test_modified_stage2_receipt_cannot_be_substituted(self):
        for key, value in (("installed_source_sha256", S.SUCCESSOR), ("stage3_allowed", False),
                           ("stage1_prerequisite", "FAIL"), ("status", "RUNNING"),
                           ("original_values_restored", False), ("independent_price_fields", "FAIL")):
            changed = dict(self.stage2, **{key: value})
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "ORIGINAL_STAGE2"):
                S.validate_source_successor(changed, S.SUCCESSOR, self.raw)

    def test_every_artifact_deletion_rejected_by_public_validator(self):
        for path in self.chain["artifacts"]:
            changed = copy.deepcopy(self.chain)
            del changed["artifacts"][path]
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "EXACT_REVIEWED_CHAIN"):
                S.validate_source_successor(self.stage2, S.SUCCESSOR, json.dumps(changed).encode())

    def test_entry_hash_failure_rejected_semantically(self):
        self.chain["artifacts"][S.STAGE2_PATH]["git_blob"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "ARTIFACT_HASH_MISMATCH"):
            S._validate_chain(self.stage2, S.SUCCESSOR, self.chain)

    def test_missing_actual_install_receipt_rejected_semantically(self):
        del self.chain["artifacts"][S.INSTALL_PATH]
        with self.assertRaisesRegex(ValueError, "MISSING_ARTIFACT"):
            S._validate_chain(self.stage2, S.SUCCESSOR, self.chain)

    def test_wrong_canonical_commit_rejected_semantically(self):
        self.chain["source_commit"] = "0" * 40
        with self.assertRaisesRegex(ValueError, "CANONICAL_COMMIT"):
            S._validate_chain(self.stage2, S.SUCCESSOR, self.chain)

    def test_rehashed_wrong_manifest_before_image_rejected(self):
        path = "tasks/manifests/" + S.TASK + ".json"
        chain = self.semantic_mutation(path, lambda d: d["operations"][0].update(expected_before_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "BOUND_HASH_MISMATCH"):
            S._validate_chain(self.stage2, S.SUCCESSOR, chain)

    def test_rehashed_foreign_transaction_rejected(self):
        path = "state/transactions/" + S.TASK + "." + S.REQUEST_SHA + "." + S.RUN + ".json"
        chain = self.semantic_mutation(path, lambda d: d.update(transaction_id="foreign-transaction"))
        with self.assertRaisesRegex(ValueError, "TRANSACTION_IDENTITY"):
            S._validate_chain(self.stage2, S.SUCCESSOR, chain)

    def test_nonterminal_or_failed_transaction_rejected(self):
        path = "state/transactions/" + S.TASK + "." + S.REQUEST_SHA + "." + S.RUN + ".json"
        for status in ("OPEN", "ROLLING_BACK", "FAILED", "UNKNOWN"):
            chain = self.semantic_mutation(path, lambda d: d.update(status=status))
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "ACCEPTED_TERMINAL_OUTCOME"):
                S._validate_chain(self.stage2, S.SUCCESSOR, chain)

    def test_actual_or_unknown_rollback_rejected(self):
        path = "state/reconciliations/" + S.TASK + "." + S.RUN + ".forward-reconciliation.json"
        for performed in (True, None, "UNKNOWN"):
            chain = self.semantic_mutation(path, lambda d: d.update(rollback_performed=performed))
            with self.subTest(performed=performed), self.assertRaisesRegex(ValueError, "FORWARD_RECONCILIATION"):
                S._validate_chain(self.stage2, S.SUCCESSOR, chain)

    def test_archived_halt_not_resolved_rejected(self):
        path = "state/reconciliations/" + S.TASK + "." + S.RUN + ".forward-reconciliation.json"
        chain = self.semantic_mutation(path, lambda d: d.update(halt_removed=False))
        with self.assertRaisesRegex(ValueError, "FORWARD_RECONCILIATION"):
            S._validate_chain(self.stage2, S.SUCCESSOR, chain)

    def test_unknown_installed_source_rejected_before_admission(self):
        chain = self.semantic_mutation(S.INSTALL_PATH, lambda d: d["receipt"]["installer"]["source_after_sha256"].update({"cars_ui.py": "0" * 64}))
        with self.assertRaisesRegex(ValueError, "BOUND_HASH_MISMATCH"):
            S._validate_chain(self.stage2, S.SUCCESSOR, chain)


if __name__ == "__main__":
    unittest.main()
