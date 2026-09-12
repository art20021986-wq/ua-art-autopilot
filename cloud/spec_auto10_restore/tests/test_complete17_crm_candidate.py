"""Four composition/admission checks; no application code is imported or run."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
WORK = HERE.parents[2]
spec = importlib.util.spec_from_file_location("crm17_builder", HERE / "complete17_crm_candidate.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CrmCandidateCompositionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="crm17-composition-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.base, self.evidence, self.output = self.root / "base", self.root / "evidence", self.root / "output"
        shutil.copytree(WORK / "private-runtime/complete-candidate17-v2", self.base)
        self.evidence.mkdir()
        for pin in builder.RECEIPTS.values():
            for name in (pin["report"], pin["summary"]):
                shutil.copy2(HERE / "evidence" / name, self.evidence / name)

    def prepare(self):
        return builder.prepare(self.base, self.evidence, self.output)

    def test_exact_one_changed_module_and_separate_server_evidence(self):
        before = {str(path.relative_to(self.base)): path.read_bytes() for path in self.base.rglob("*") if path.is_file()}
        imported = set(sys.modules)
        manifest = self.prepare()
        self.assertEqual(manifest, builder.verify(self.output, self.base, self.evidence))
        self.assertEqual({name for name in manifest["files"] if (self.output / name).read_bytes() != before[name]}, {"cars_ui.py"})
        self.assertEqual(builder.sha((self.output / "cars_ui.py").read_bytes()), builder.PATCHED_UI_SHA)
        self.assertEqual(before, {str(path.relative_to(self.base)): path.read_bytes() for path in self.base.rglob("*") if path.is_file()})
        self.assertEqual(set(manifest["execution_evidence"]), {"combined_v2", "callback_delta"})
        self.assertEqual(manifest["overall_gate_b"], "NOT_EVALUATED")
        self.assertFalse(manifest["production_changed"])
        self.assertFalse((set(sys.modules) - imported) & {Path(name).stem for name in manifest["files"]})

    def test_byte_drift_missing_nested_module_and_extra_file_refused(self):
        nested = self.base / "autopilot_inbox/cloud/task_083_catalog_dedup/installer.py"
        old = nested.read_bytes()
        nested.write_bytes(old + b"\n# unreviewed change\n")
        with self.assertRaisesRegex(RuntimeError, "INPUT_SHA_MISMATCH"):
            self.prepare()
        nested.unlink()
        with self.assertRaisesRegex(RuntimeError, "BASE17_EXACT_FILE_SET_REQUIRED"):
            self.prepare()
        nested.write_bytes(old)
        (self.base / "installer.py").write_bytes(old)
        with self.assertRaisesRegex(RuntimeError, "BASE17_EXACT_FILE_SET_REQUIRED"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_edited_pass_receipt_does_not_authorize_composition(self):
        path = self.evidence / builder.RECEIPTS["callback_delta"]["report"]
        value = json.loads(path.read_text())
        value["ui_patch"]["after_sha256"] = builder.SOURCE_UI_SHA
        value["status"] = "PASS"
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(RuntimeError, "INPUT_SHA_MISMATCH"):
            self.prepare()
        self.assertFalse(self.output.exists())

    def test_existing_output_and_symlinked_input_refused(self):
        with self.assertRaisesRegex(RuntimeError, "INPUT_OUTPUT_OVERLAP"):
            builder.prepare(self.base, self.evidence, self.root / "away" / ".." / "base" / "unwanted")
        self.assertFalse((self.base / "unwanted").exists())
        self.output.mkdir()
        note = self.output / "operator-note.txt"
        note.write_text("keep")
        with self.assertRaisesRegex(RuntimeError, "OUTPUT_MUST_BE_NEW_CANONICAL_DIRECTORY"):
            self.prepare()
        self.assertEqual(note.read_text(), "keep")
        source = self.base / "cars_ui.py"
        saved = self.root / "saved-ui.py"
        source.rename(saved)
        source.symlink_to(saved)
        with self.assertRaisesRegex(RuntimeError, "SYMLINK"):
            self.prepare()
        self.assertEqual(note.read_text(), "keep")


if __name__ == "__main__":
    unittest.main(verbosity=2)
