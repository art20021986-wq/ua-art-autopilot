"""Exercise existing installer gates with a historical source successor.

New install records are deliberately synthetic TEST evidence in temporary roots.
The only genuine evidence reused is the immutable completed historical chain.
No file installation or live source observation is performed by these tests.
"""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import install_package as I
import source_successor as S
import test_install_package as fixtures


class SourceSuccessorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InstallTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        self.f.before["cars_ui.py"] = S.SUCCESSOR
        self.f.bind()
        self.chain_raw = (Path(__file__).parent / S.SOURCE_SUCCESSOR_BINDING["file"]).read_bytes()
        self.f.evidence["stage2"] = json.loads(self.chain_raw)["artifacts"][S.STAGE2_PATH]["raw"].encode()
        self.f.evidence["source_successor"] = self.chain_raw
        self.f.plan["source_successor"] = dict(S.SOURCE_SUCCESSOR_BINDING)
        manifest = json.loads(self.f.evidence["manifest"])
        manifest["deployment_plan"] = {"source_successor_sha256": I.sha(self.chain_raw)}
        self.f.evidence["manifest"] = I.encoded(manifest)
        self.rebind_test_records()

    def rebind_test_records(self):
        e = self.f.evidence
        manifest_sha = I.sha(e["manifest"])
        gate, request, owner, claim, transaction = (json.loads(e[name]) for name in
            ("gate_b", "request", "owner_approval", "claim", "transaction"))
        gate["manifest_sha256"] = manifest_sha
        e["gate_b"] = I.encoded(gate)
        request["critical"].update(manifest_sha256=manifest_sha, gate_a_sha256=I.sha(e["gate_b"]), owner_approval_sha256="0"*64)
        subject = (json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        owner.update(manifest_sha256=manifest_sha, gate_a_sha256=I.sha(e["gate_b"]), request_subject_sha256=I.sha(subject))
        e["owner_approval"] = I.encoded(owner)
        request["critical"]["owner_approval_sha256"] = I.sha(e["owner_approval"])
        e["request"] = I.encoded(request)
        claim["identity"]["task_sha256"] = transaction["request_sha256"] = I.sha(e["request"])
        e["claim"], e["transaction"] = I.encoded(claim), I.encoded(transaction)
        self.f.plan["evidence_sha256"] = {k:I.sha(v) for k,v in e.items()}

    def validate(self):
        return I._validate(self.f.plan, self.f.files, self.f.evidence, self.f.now, self.f.root, testing=True)

    def test_explicit_successor_admitted_after_all_existing_gates(self):
        original = self.f.evidence["stage2"]
        self.validate()
        self.assertEqual(original, self.f.evidence["stage2"])
        self.assertEqual(json.loads(original)["installed_source_sha256"], S.PREDECESSOR)

    def test_no_successor_binding_keeps_original_strict_source_guard(self):
        del self.f.plan["source_successor"]
        del self.f.evidence["source_successor"]
        self.rebind_test_records()
        with self.assertRaisesRegex(I.InstallError, "CANONICAL_STAGE2_ACCEPTANCE"):
            self.validate()

    def test_null_or_unknown_binding_rejected(self):
        for value in (None, {}, dict(S.SOURCE_SUCCESSOR_BINDING, sha256="0"*64)):
            self.f.plan["source_successor"] = value
            with self.subTest(value=value), self.assertRaisesRegex(I.InstallError, "BOUND_CANONICAL_SOURCE_SUCCESSOR"):
                self.validate()

    def test_successor_absent_from_exact_evidence_set_rejected(self):
        del self.f.evidence["source_successor"]
        self.rebind_test_records()
        with self.assertRaisesRegex(I.InstallError, "COMPLETE_CANONICAL_EVIDENCE"):
            self.validate()

    def test_chain_tamper_rebound_to_new_test_authorization_still_rejected(self):
        self.f.evidence["source_successor"] += b"\n"
        manifest = json.loads(self.f.evidence["manifest"])
        manifest["deployment_plan"]["source_successor_sha256"] = I.sha(self.f.evidence["source_successor"])
        self.f.evidence["manifest"] = I.encoded(manifest)
        self.rebind_test_records()
        with self.assertRaisesRegex(I.InstallError, "CANONICAL_SOURCE_SUCCESSOR_INVALID"):
            self.validate()

    def test_missing_or_wrong_approved_manifest_binding_rejected(self):
        for value in ({}, {"source_successor_sha256":"0"*64}):
            manifest = json.loads(self.f.evidence["manifest"])
            manifest["deployment_plan"] = value
            self.f.evidence["manifest"] = I.encoded(manifest)
            self.rebind_test_records()
            with self.subTest(value=value), self.assertRaisesRegex(I.InstallError, "BOUND_CANONICAL_SOURCE_SUCCESSOR"):
                self.validate()

    def test_historical_chain_never_replaces_current_preview_gate(self):
        preview = json.loads(self.f.evidence["preview_gate"])
        preview["checks"]["photos"] = "FAIL"
        self.f.evidence["preview_gate"] = I.encoded(preview)
        gate = json.loads(self.f.evidence["gate_b"])
        gate["preview_gate_sha256"] = I.sha(self.f.evidence["preview_gate"])
        self.f.evidence["gate_b"] = I.encoded(gate)
        self.rebind_test_records()
        with self.assertRaisesRegex(I.InstallError, "FULL_BOUND_PREVIEW_GATE"):
            self.validate()

    def test_successor_never_permits_unfenced_writer(self):
        writers = json.loads(self.f.evidence["writers"])
        writers["writers"][0]["fence"] = "UNKNOWN"
        self.f.evidence["writers"] = I.encoded(writers)
        gate = json.loads(self.f.evidence["gate_b"])
        gate["writer_fence_report_sha256"] = I.sha(self.f.evidence["writers"])
        self.f.evidence["gate_b"] = I.encoded(gate)
        self.rebind_test_records()
        with self.assertRaisesRegex(I.InstallError, "WRITER"):
            self.validate()

    def test_engine_rejects_changed_sibling_validator(self):
        read = I._read
        def changed(path):
            raw = read(path)
            return raw + b"\n" if Path(path).name == "source_successor.py" else raw
        with patch.object(I, "_read", side_effect=changed), self.assertRaisesRegex(I.InstallError, "EXACT_SOURCE_SUCCESSOR_VALIDATOR"):
            self.validate()

    def test_engine_ignores_foreign_sys_modules_validator(self):
        import sys
        import types
        foreign = types.ModuleType("source_successor")
        foreign.validate_source_successor = lambda *a: self.fail("unreviewed cached validator called")
        with patch.dict(sys.modules, {"source_successor": foreign}):
            self.validate()


if __name__ == "__main__":
    unittest.main()
