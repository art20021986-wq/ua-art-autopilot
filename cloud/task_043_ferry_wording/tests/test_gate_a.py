import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_a


class TestGateA(unittest.TestCase):
    def setUp(self):
        self.source_root = tempfile.mkdtemp()
        self.staging_root = tempfile.mkdtemp()
        self.preview_root = tempfile.mkdtemp()
        self.report_root = tempfile.mkdtemp()
        html_content = '<html><body><span data-stage="sea" data-ru="В море">В море</span></body></html>'
        with open(os.path.join(self.source_root, "UA-0001.html"), "w", encoding="utf-8") as fh:
            fh.write(html_content)

    def tearDown(self):
        for d in (self.source_root, self.staging_root, self.preview_root, self.report_root):
            shutil.rmtree(d, ignore_errors=True)

    def _build(self):
        return gate_a.build_gate_a(
            self.source_root, ["UA-0001.html"], self.staging_root, self.preview_root, self.report_root,
            preview_allowed_root=self.preview_root, report_allowed_root=self.report_root,
            staging_allowed_root=self.staging_root,
        )

    def test_build_and_byte_identity_across_two_runs(self):
        r1 = self._build()
        sha_after_1 = r1["manifest"]["files"][0]["sha_after"]
        shutil.rmtree(self.staging_root); os.makedirs(self.staging_root)
        shutil.rmtree(self.preview_root); os.makedirs(self.preview_root)
        r2 = self._build()
        sha_after_2 = r2["manifest"]["files"][0]["sha_after"]
        self.assertEqual(sha_after_1, sha_after_2)

    def test_internal_stage_marker_preserved(self):
        self._build()
        staged = os.path.join(self.preview_root, "UA-0001.html")
        with open(staged, "r", encoding="utf-8") as fh:
            content = fh.read()
        self.assertIn('data-stage="sea"', content)
        self.assertIn(">Паром<", content)

    def test_path_escape_rejected(self):
        r1 = gate_a.build_gate_a(
            self.source_root, ["../evil.html"], self.staging_root, self.preview_root, self.report_root,
            preview_allowed_root=self.preview_root, report_allowed_root=self.report_root,
            staging_allowed_root=self.staging_root,
        )
        self.assertTrue(any("escape" in b["reason"] for b in r1["manifest"]["blocked"]))

    def test_ambiguous_python_source_blocked(self):
        with open(os.path.join(self.source_root, "stranica.py"), "w", encoding="utf-8") as fh:
            fh.write("STATUS = 'В море'\n")
        r1 = gate_a.build_gate_a(
            self.source_root, ["stranica.py"], self.staging_root, self.preview_root, self.report_root,
            preview_allowed_root=self.preview_root, report_allowed_root=self.report_root,
            staging_allowed_root=self.staging_root,
        )
        self.assertTrue(any("AMBIGUOUS" in b["reason"] for b in r1["manifest"]["blocked"]))

    def test_root_escape_blocked_before_write(self):
        with self.assertRaises(gate_a.GateABlocked):
            gate_a.build_gate_a(
                self.source_root, ["UA-0001.html"], "/tmp/not-allowed-staging", self.preview_root, self.report_root,
                preview_allowed_root=self.preview_root, report_allowed_root=self.report_root,
                staging_allowed_root=self.staging_root,
            )

    def test_determinism_10_runs(self):
        ok, hashes = gate_a.determinism_check(
            self.source_root, ["UA-0001.html"], lang_for_file={"UA-0001.html": "ru"}, runs=10
        )
        self.assertTrue(ok)
        self.assertEqual(len(hashes), 1)


if __name__ == "__main__":
    unittest.main()
