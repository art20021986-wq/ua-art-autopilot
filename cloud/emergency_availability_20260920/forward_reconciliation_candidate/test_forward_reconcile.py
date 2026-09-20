import json
import pathlib
import shutil
import tempfile
import unittest

import forward_reconcile as fr


HERE = pathlib.Path(__file__).resolve().parent


class ForwardReconcileTests(unittest.TestCase):
    def make_root(self, folder):
        root = pathlib.Path(folder) / "repo"
        mapping = {
            fr.TX_REL: "tx.json", fr.CLAIM_REL: "claim.json", fr.HALT_REL: "halt.json",
            fr.BACKUP_REL: "backup.json", fr.REQUEST_REL: "request.json",
        }
        for relative, source in mapping.items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(HERE / "fixtures" / source, target)
        return root

    def test_exact_candidate(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_root(folder)
            plan, out = fr.build(root, HERE / "fixtures/live.json", "2026-09-20T08:57:00Z")
            self.assertFalse(plan["ready"])
            self.assertTrue(plan["review_required"])
            self.assertEqual(len(plan["changes"]), 8)
            self.assertEqual(json.loads(out[fr.TX_REL])["status"], "FINISHED")
            claim = json.loads(out[fr.CLAIM_REL])
            self.assertEqual(claim["task_execution_status"], "FINISHED")
            self.assertEqual(claim["production_transaction_status"], "FINISHED")
            receipt = json.loads(out[fr.RECEIPT_REL])
            self.assertEqual(receipt["rollback"], "NOT_PERFORMED")
            self.assertEqual(receipt["live_verify"], "PASS")
            self.assertEqual(out[fr.HISTORY_HALT_REL], (root / fr.HALT_REL).read_bytes())
            self.assertTrue((root / fr.HALT_REL).exists())

    def test_input_drift_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_root(folder)
            (root / fr.TX_REL).write_text("{}\n")
            with self.assertRaisesRegex(fr.ReconcileError, "INPUT_SHA256"):
                fr.build(root, HERE / "fixtures/live.json", "2026-09-20T08:57:00Z")

    def test_wrong_live_outcome_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_root(folder)
            live = pathlib.Path(folder) / "live.json"
            value = json.loads((HERE / "fixtures/live.json").read_text())
            value["live_availability"]["availability_outcome"] = "UNKNOWN"
            live.write_text(json.dumps(value))
            original = fr.INPUT_SHA256["external/live.json"]
            fr.INPUT_SHA256["external/live.json"] = fr.sha(live.read_bytes())
            try:
                with self.assertRaisesRegex(fr.ReconcileError, "LIVE_AVAILABILITY"):
                    fr.build(root, live, "2026-09-20T08:57:00Z")
            finally:
                fr.INPUT_SHA256["external/live.json"] = original

    def test_halt_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_root(folder)
            halt = root / fr.HALT_REL
            value = json.loads(halt.read_text())
            value["task_id"] = "OTHER"
            halt.write_text(json.dumps(value))
            original = fr.INPUT_SHA256[fr.HALT_REL]
            fr.INPUT_SHA256[fr.HALT_REL] = fr.sha(halt.read_bytes())
            try:
                with self.assertRaisesRegex(fr.ReconcileError, "HALT_IDENTITY"):
                    fr.build(root, HERE / "fixtures/live.json", "2026-09-20T08:57:00Z")
            finally:
                fr.INPUT_SHA256[fr.HALT_REL] = original

    def test_output_scope_has_no_runtime_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.make_root(folder)
            plan, _ = fr.build(root, HERE / "fixtures/live.json", "2026-09-20T08:57:00Z")
            paths = {item["path"] for item in plan["changes"]}
            self.assertNotIn("cars_ui.py", paths)
            self.assertNotIn("stranica.py", paths)
            self.assertTrue(all(path.startswith("state/") for path in paths))


if __name__ == "__main__":
    unittest.main()
