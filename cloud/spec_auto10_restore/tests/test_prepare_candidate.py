"""Offline compiler tests with temporary snapshots and no application execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compiler = load("offline_candidate_compiler", HERE.parent / "prepare_candidate.py")
fixtures = load("offline_candidate_source_fixtures", HERE / "test_integration.py")


class CandidateCompilerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "snapshot"
        self.source.mkdir()
        self.output = self.root / "candidate"
        self.sources = {
            "ua_additional_spec.py": fixtures.spec_source(),
            "publikaciya.py": fixtures.publisher_source(),
            "publish_transaction_guard.py": fixtures.BASE_GUARD,
            "cars_ui.py": fixtures.crm_source(),
        }
        for name, text in self.sources.items():
            (self.source / name).write_text(text, encoding="utf-8")

    def test_compiles_complete_candidate_without_executing_sources_or_changing_inputs(self):
        # A real application import would fail immediately. Compilation is safe.
        with (self.source / "publikaciya.py").open("a") as handle:
            handle.write("\nraise RuntimeError('APPLICATION_MUST_NOT_EXECUTE')\n")
        runtime = self.root / "runtime"
        runtime.mkdir()
        for name in compiler.RUNTIME_FILES:
            (runtime / name).write_bytes(
                (compiler.RUNTIME / name).read_bytes() + b"\nraise RuntimeError('RUNTIME_MUST_NOT_EXECUTE')\n"
            )
        paths = list(self.source.iterdir()) + list(runtime.iterdir())
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
        with patch.object(compiler, "RUNTIME", runtime):
            report = compiler.prepare(self.source, self.output)
        after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in paths}
        self.assertEqual(before, after)
        self.assertEqual(report["module_count"], 8)
        self.assertFalse(report["production_changed"])
        self.assertFalse(report["runtime_verified"])
        self.assertEqual(set(p.name for p in self.output.iterdir()), set(compiler.SNAPSHOT_FILES + compiler.RUNTIME_FILES) | {"manifest.json"})
        saved = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(saved, report)
        for name, item in report["files"].items():
            original = self.source / name if name in compiler.SNAPSHOT_FILES else runtime / name
            self.assertEqual(item["before_sha256"], hashlib.sha256(original.read_bytes()).hexdigest())
            self.assertEqual(item["after_sha256"], hashlib.sha256((self.output / name).read_bytes()).hexdigest())
            compile((self.output / name).read_text(), name, "exec")
            if name in compiler.RUNTIME_FILES:
                self.assertEqual(original.read_bytes(), (self.output / name).read_bytes())
        self.assertEqual(list(self.root.glob(".spec-candidate-*")), [])

    def test_unknown_or_missing_sources_leave_no_partial_output(self):
        source_file = self.source / "cars_ui.py"
        original = source_file.read_text()
        for invalid in ["def broken(:\n", original.replace("_ua110_vin_service.start_worker()", "pass")]:
            source_file.write_text(invalid)
            with self.assertRaises(compiler.CandidateError):
                compiler.prepare(self.source, self.output)
            self.assertFalse(self.output.exists())
            self.assertEqual(list(self.root.glob(".spec-candidate-*")), [])
        source_file.write_text(original)
        guard = self.source / "publish_transaction_guard.py"
        nested = self.source / "unknown_nested_directory"
        nested.mkdir()
        guard.rename(nested / guard.name)
        with self.assertRaisesRegex(compiler.CandidateError, "FLATTENED_SNAPSHOT_FILES_MISSING"):
            compiler.prepare(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_refuses_existing_output_overlap_and_source_or_output_symlinks(self):
        self.output.mkdir()
        protected = self.output / "existing.txt"
        protected.write_text("keep existing output")
        with self.assertRaisesRegex(compiler.CandidateError, "OUTPUT_ALREADY_EXISTS"):
            compiler.prepare(self.source, self.output)
        self.assertEqual(protected.read_text(), "keep existing output")
        for output in [self.source, self.source / "new", self.root]:
            with self.assertRaisesRegex(compiler.CandidateError, "OVERLAP"):
                compiler.prepare(self.source, output)
        source_link = self.root / "source-link"
        source_link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(compiler.CandidateError, "SYMLINK"):
            compiler.prepare(source_link, self.root / "new-output")
        destination_link = self.root / "destination-link"
        destination_link.symlink_to(self.output, target_is_directory=True)
        with self.assertRaisesRegex(compiler.CandidateError, "SYMLINK"):
            compiler.prepare(self.source, destination_link / "child")
        source_file = self.source / "cars_ui.py"
        data_file = self.root / "cars-data.py"
        source_file.rename(data_file)
        source_file.symlink_to(data_file)
        with self.assertRaisesRegex(compiler.CandidateError, "SYMLINK"):
            compiler.prepare(self.source, self.root / "new-output")
        self.assertFalse((self.root / "new-output").exists())

    def test_atomic_publication_never_replaces_output_created_concurrently(self):
        real_rename = compiler._rename_new_directory

        def simulate_competing_output(stage, output):
            output.mkdir()
            (output / "owner.txt").write_text("created by another operation")
            real_rename(stage, output)

        with patch.object(compiler, "_rename_new_directory", side_effect=simulate_competing_output):
            with self.assertRaisesRegex(compiler.CandidateError, "OUTPUT_ALREADY_EXISTS"):
                compiler.prepare(self.source, self.output)
        self.assertEqual((self.output / "owner.txt").read_text(), "created by another operation")
        self.assertEqual([p.name for p in self.output.iterdir()], ["owner.txt"])
        self.assertEqual(list(self.root.glob(".spec-candidate-*")), [])


if __name__ == "__main__":
    unittest.main()
