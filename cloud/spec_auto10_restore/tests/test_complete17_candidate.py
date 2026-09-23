"""Exact private captures; assembly-only checks, no application imports."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
WORK = HERE.parents[2]
spec = importlib.util.spec_from_file_location("complete17_under_test", HERE / "complete17_candidate.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Complete17Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="complete17-tests-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.base = root / "base"
        shutil.copytree(WORK / "private-runtime/complete-candidate15-v1-r2", self.base)
        raw = root / "raw"
        raw.mkdir()
        source_paths = {
            "analitika_wsgi.py": WORK / "private-runtime/writer-inputs-20260909T0920Z/analitika_wsgi.py",
            builder.TASK083_TARGET: WORK / "private-runtime/publisher-inputs-20260909T074529Z/autopilot_inbox/cloud/task_083_catalog_dedup/installer.py",
        }
        self.sources, self.patchers = {}, {}
        for target, source in source_paths.items():
            path = raw / ("analytics.py" if target == "analitika_wsgi.py" else "task083.py")
            shutil.copy2(source, path)
            self.sources[target] = path
        for target, name in [("analitika_wsgi.py", "patch_analytics_writer.py"), (builder.TASK083_TARGET, "patch_task083_writer.py")]:
            path = raw / name
            shutil.copy2(WORK / "route-work/cloud/writer_coordination_001" / name, path)
            self.patchers[target] = path
        self.output = root / "result"

    def build(self):
        return builder.prepare(self.base, self.sources, self.patchers, self.output)

    def test_exact17_nested_target_base_unchanged_and_no_app_import(self):
        before = {path.name: builder.read(path) for path in self.base.iterdir()}
        imported = set(sys.modules)
        result = self.build()
        self.assertEqual(result, builder.verify(self.output, self.base))
        self.assertEqual(len(result["files"]), 17)
        self.assertEqual(result["combined17_execution"], "NOT_RUN")
        self.assertFalse(result["production_changed"])
        self.assertTrue((self.output / builder.TASK083_TARGET).is_file())
        self.assertFalse((self.output / "installer.py").exists())
        self.assertEqual(before, {path.name: builder.read(path) for path in self.base.iterdir()})
        self.assertFalse((set(sys.modules) - imported) & {Path(name).stem for name in result["files"]})

    def test_source_or_patcher_drift_rejected_before_output(self):
        for path in (self.sources["analitika_wsgi.py"], self.patchers[builder.TASK083_TARGET]):
            old = path.read_bytes()
            path.write_bytes(old + b"\n# drift\n")
            with self.assertRaisesRegex(RuntimeError, "INPUT_SHA_MISMATCH"):
                self.build()
            path.write_bytes(old)
            self.assertFalse(self.output.exists())

    def test_base_drift_rejected_without_touching_output(self):
        path = self.base / "db.py"
        path.write_bytes(path.read_bytes() + b"\n# drift\n")
        with self.assertRaises(RuntimeError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_existing_output_and_nested_base_output_rejected(self):
        self.output.mkdir()
        sentinel = self.output / "owner.txt"
        sentinel.write_text("unchanged")
        with self.assertRaisesRegex(RuntimeError, "OUTPUT_ALREADY_EXISTS"):
            self.build()
        self.assertEqual(sentinel.read_text(), "unchanged")
        with self.assertRaisesRegex(RuntimeError, "INPUT_OUTPUT_OVERLAP"):
            builder.prepare(self.base, self.sources, self.patchers, self.base / "output")

    def test_missing_mapping_symlink_and_flattened_target_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "EXACT_WRITER_MAPPING_REQUIRED"):
            builder.prepare(self.base, {"installer.py": self.sources[builder.TASK083_TARGET]}, self.patchers, self.output)
        path = self.sources["analitika_wsgi.py"]
        saved = path.with_suffix(".saved")
        path.rename(saved)
        path.symlink_to(saved)
        with self.assertRaisesRegex(RuntimeError, "SYMLINK_FORBIDDEN"):
            self.build()

    def test_mid_assembly_input_drift_leaves_no_ready_manifest(self):
        original = builder.recheck
        calls = 0
        def recheck(inputs):
            nonlocal calls
            calls += 1
            if calls == 2:
                path = self.sources[builder.TASK083_TARGET]
                path.write_bytes(path.read_bytes() + b"\n# concurrent drift\n")
            return original(inputs)
        with patch.object(builder, "recheck", side_effect=recheck):
            with self.assertRaisesRegex(RuntimeError, "INPUT_SHA_MISMATCH"):
                self.build()
        self.assertFalse((self.output / "manifest.json").exists())

    def test_manifest_cannot_claim_execution_or_accept_flattened_tree(self):
        self.build()
        path = self.output / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["combined17_execution"] = "PASS"
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RuntimeError, "MANIFEST_SCOPE_OR_PROVENANCE_MISMATCH"):
            builder.verify(self.output, self.base)
        manifest["combined17_execution"] = "NOT_RUN"
        path.write_text(json.dumps(manifest))
        (self.output / builder.TASK083_TARGET).rename(self.output / "installer.py")
        with self.assertRaisesRegex(RuntimeError, "EXACT17_FILE_SET_REQUIRED"):
            builder.verify(self.output, self.base)

    def test_manifest_fsync_failure_invalidates_own_readiness(self):
        real_fsync = os.fsync
        failed = []
        def fsync(fd):
            if os.readlink("/proc/self/fd/" + str(fd)).endswith("/result/manifest.json") and not failed:
                failed.append(True)
                raise OSError("injected manifest fsync failure")
            return real_fsync(fd)
        with patch.object(builder.os, "fsync", side_effect=fsync):
            with self.assertRaisesRegex(OSError, "manifest fsync failure"):
                self.build()
        self.assertTrue(failed)
        self.assertFalse((self.output / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
