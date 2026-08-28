import hashlib
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import discover
import gate_a_controller
import gate_a_remote


class FerryGateATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="ferry_gate_a_")
        self.source = Path(self.temp) / "source"
        self.candidates = Path(self.temp) / "candidates"
        self.source.mkdir()
        self._build_root()

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def _build_root(self):
        for rel_path in discover.REGISTRY["video_pages"]:
            path = self.source / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                '<html><body><div class="status-pill">В море</div></body></html>',
                encoding="utf-8",
            )
        for rel_path in discover.REGISTRY["python_modules"]:
            (self.source / rel_path).write_text("def f():\n    return 1\n", encoding="utf-8")
        conn = sqlite3.connect(str(self.source / "crm.db"))
        conn.execute(
            "CREATE TABLE cars (auto_number TEXT, sea_container TEXT, status TEXT)"
        )
        for number in range(1, 11):
            conn.execute(
                "INSERT INTO cars VALUES (?,?,?)",
                ("UA-%04d" % number, "CONT%03d" % number, "sea"),
            )
        conn.commit()
        conn.close()

    def _source_hashes(self):
        return {
            rel_path: hashlib.sha256((self.source / rel_path).read_bytes()).hexdigest()
            for rel_path in discover.REGISTRY["video_pages"]
        }

    def test_remote_gate_builds_only_isolated_candidates(self):
        before = self._source_hashes()
        receipt = gate_a_remote._run_gate_a(
            str(self.source), str(self.candidates), False
        )
        self.assertEqual(receipt["status"], "PASS", receipt)
        self.assertTrue(receipt["production_sources_unchanged"])
        self.assertEqual(len(receipt["candidates"]), 14)
        self.assertEqual(sum(item["changes"] for item in receipt["candidates"]), 14)
        self.assertEqual(self._source_hashes(), before)
        self.assertFalse(receipt["production_write"])
        self.assertFalse(receipt["crm_write"])
        self.assertFalse(receipt["ua0009_published"])
        for rel_path in discover.REGISTRY["video_pages"]:
            candidate = (self.candidates / rel_path).read_text(encoding="utf-8")
            self.assertIn("На пароме", candidate)
            self.assertNotIn(">В море<", candidate)

    def test_user_facing_generator_literal_is_reported(self):
        (self.source / "cars_ui.py").write_text(
            'STATUS_LABEL = "В море"\n', encoding="utf-8"
        )
        receipt = gate_a_remote._run_gate_a(
            str(self.source), str(self.candidates), False
        )
        self.assertEqual(receipt["status"], "PASS_READY_FOR_GATE_B", receipt)
        self.assertTrue(any(
            item["path"] == "cars_ui.py" and item["classification"] == "USER_FACING"
            for item in receipt["python_sources"]
        ))
        self.assertEqual(len(receipt["generator_candidates"]), 1)
        candidate = self.candidates / "python" / "cars_ui.py"
        self.assertEqual(candidate.read_text(encoding="utf-8"), 'STATUS_LABEL = "На пароме"\n')
        self.assertEqual(receipt["generator_candidates"][0]["changes"], 1)
        receipt["source_root"] = "/home/Carix"
        receipt["candidate_root"] = gate_a_controller.REMOTE_ROOT + "/gate_a_candidates"
        validated = gate_a_controller.GateAController.validate_receipt(receipt)
        self.assertEqual(validated["status"], "PASS_READY_FOR_GATE_B")

    def test_ambiguous_generator_literal_blocks(self):
        (self.source / "cars_ui.py").write_text('x = "В море"\n', encoding="utf-8")
        receipt = gate_a_remote._run_gate_a(
            str(self.source), str(self.candidates), False
        )
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("AMBIGUOUS_TARGET", receipt["discovery_reasons"])

    def test_candidate_symlink_parent_blocks(self):
        self.candidates.mkdir()
        outside = Path(self.temp) / "outside"
        outside.mkdir()
        os.symlink(str(outside), str(self.candidates / "video"))
        receipt = gate_a_remote._run_gate_a(
            str(self.source), str(self.candidates), False
        )
        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("candidate_parent_symlink", receipt["errors"])

    def test_controller_validates_remote_pass_receipt(self):
        receipt = gate_a_remote._run_gate_a(
            str(self.source), str(self.candidates), False
        )
        receipt["source_root"] = "/home/Carix"
        receipt["candidate_root"] = gate_a_controller.REMOTE_ROOT + "/gate_a_candidates"
        validated = gate_a_controller.GateAController.validate_receipt(receipt)
        self.assertEqual(validated["status"], "PASS")

    def test_controller_rejects_unsafe_flag(self):
        receipt = gate_a_remote._run_gate_a(
            str(self.source), str(self.candidates), False
        )
        receipt["source_root"] = "/home/Carix"
        receipt["candidate_root"] = gate_a_controller.REMOTE_ROOT + "/gate_a_candidates"
        receipt["production_write"] = True
        with self.assertRaises(gate_a_controller.ControllerBlocked):
            gate_a_controller.GateAController.validate_receipt(receipt)

    def test_controller_api_file_allowlist(self):
        api = gate_a_controller.PythonAnywhereAPI(
            "Carix", "www.pythonanywhere.com", "test-token"
        )
        with self.assertRaises(gate_a_controller.ControllerBlocked):
            api._file_url("/home/Carix/video/UA-0001.html")

    def test_local_preview_path_allowlist(self):
        self.assertEqual(
            gate_a_controller.GateAController.preview_path(
                "video/UA-0001.html", generator=False
            ),
            gate_a_controller.PREVIEW_ROOT / "video" / "UA-0001.html",
        )
        with self.assertRaises(gate_a_controller.ControllerBlocked):
            gate_a_controller.GateAController.preview_path(
                "../../video/UA-0001.html", generator=False
            )

    def test_controller_full_fake_relay(self):
        receipt = gate_a_remote._run_gate_a(
            str(self.source), str(self.candidates), False
        )
        receipt["source_root"] = "/home/Carix"
        receipt["candidate_root"] = gate_a_controller.REMOTE_ROOT + "/gate_a_candidates"

        class FakeAPI:
            def __init__(self, payload, candidates):
                self.payload = payload
                self.candidates = candidates
                self.uploads = {}
                self.cleaned = False

            def upload_script(self, remote, data):
                self.uploads[remote] = data

            def read_file(self, path):
                if path == gate_a_controller.REMOTE_OUTPUT:
                    return json_bytes(self.payload)
                if path in self.uploads:
                    return self.uploads[path]
                rel_path = next(
                    rel for rel, remote in gate_a_controller.REMOTE_CANDIDATES.items()
                    if remote == path
                )
                return (candidates / rel_path).read_bytes()

            def delete_output(self):
                self.cleaned = True

            def create_trigger(self):
                return ("always_on", 1)

            def delete_trigger(self, trigger):
                self.cleaned = True

        def json_bytes(value):
            import json
            return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")

        candidates = self.candidates
        api = FakeAPI(receipt, candidates)
        evidence = Path(self.temp) / "evidence.json"
        report = Path(self.temp) / "report.md"
        with mock.patch.object(gate_a_controller, "EVIDENCE_PATH", evidence), mock.patch.object(
            gate_a_controller, "REPORT_PATH", report
        ), mock.patch.object(
            gate_a_controller, "PREVIEW_ROOT", Path(self.temp) / "preview"
        ):
            result = gate_a_controller.GateAController(
                api, sleep=lambda _seconds: None, monotonic=lambda: 0,
                poll_interval=0, poll_timeout=1,
            ).run()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(api.cleaned)
        self.assertTrue(evidence.is_file())
        self.assertTrue(report.is_file())
        self.assertIn("production_write: false", report.read_text(encoding="utf-8"))
        self.assertEqual(
            len(list((Path(self.temp) / "preview" / "video").glob("*.html"))), 14
        )


if __name__ == "__main__":
    unittest.main()
