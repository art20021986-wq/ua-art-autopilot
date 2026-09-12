"""Exact-capture composition and failure gates; no application execution."""
import errno
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
spec = importlib.util.spec_from_file_location('complete_candidate_under_test', HERE/'complete_candidate.py')
assembler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembler)
CAPTURES = Path(os.environ.get('UA_ART_COMPLETE_CAPTURE_ROOT', str(HERE.parents[2]/'private-runtime')))


class CompleteCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (CAPTURES/'candidate-errno22-v7/manifest.json').is_file():
            raise unittest.SkipTest('Explicit reviewed private source captures required')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root/'base-v7'
        self.base.mkdir()
        for name in set(assembler.BASE_PINS) | {'manifest.json'}:
            shutil.copy2(CAPTURES/'candidate-errno22-v7'/name, self.base/name)
        raw = self.root/'raw-captures'
        raw.mkdir()
        capture_paths = {name: CAPTURES/'publisher-inputs-20260909T074529Z'/name
                         for name in ('master_card.py', 'db.py', 'stranica.py', 'catalog_design_guard.py')}
        capture_paths.update({
            'cars_schema.py': CAPTURES/'publisher-inputs-20260909T074936Z/cars_schema.py',
            'ai_filter.py': CAPTURES/'publisher-inputs-20260909T075542Z/ai_filter.py',
            'catalog_design_golden.html': CAPTURES/'publisher-inputs-20260909T074856Z/catalog_design_golden.html',
        })
        self.sources = {}
        for name, source in capture_paths.items():
            shutil.copy2(source, raw/name)
            self.sources[name] = raw/name
        self.output = self.root/'complete-candidate'

    def build(self):
        return assembler.prepare(self.base, self.sources, self.output)

    def test_real_composition_exact15_pins_and_historical_builder_stays10(self):
        before = {str(path): assembler._read_input(path) for path in self.base.iterdir()}
        imported = set(sys.modules)
        report = self.build()
        self.assertEqual(report, assembler.verify_candidate(self.output))
        self.assertEqual(report['module_count'], 15)
        self.assertEqual(report['publication_mode'], 'manifest_last')
        self.assertEqual({p.name for p in self.output.iterdir()}, set(assembler.COMPLETE_FILES) | {'manifest.json'})
        self.assertEqual({name: assembler.sha((self.output/name).read_bytes()) for name in assembler.COMPLETE_FILES}, assembler.OUTPUT_PINS)
        self.assertEqual(before, {str(path): assembler._read_input(path) for path in self.base.iterdir()})
        application_names = {Path(name).stem for name in assembler.COMPLETE_FILES}
        self.assertFalse((set(sys.modules)-imported) & application_names)
        old = assembler._io_helpers()
        self.assertEqual(old.verify_candidate(self.base)['module_count'], 10)
        with self.assertRaisesRegex(RuntimeError, 'FILE_SET_INVALID'):
            old.verify_candidate(self.output)

    def test_missing_and_unexpected_source_mapping_rejected_before_output(self):
        for sources in ({key: value for key, value in self.sources.items() if key != 'db.py'},
                        dict(self.sources, unknown='unknown.py')):
            with self.assertRaisesRegex(assembler.CandidateError, 'EXACT_SOURCE_MAPPING_REQUIRED'):
                assembler.prepare(self.base, sources, self.output)
        self.assertFalse(self.output.exists())

    def test_missing_and_unexpected_base_files_rejected(self):
        (self.base/'unknown.py').write_text('pass\n')
        with self.assertRaisesRegex(RuntimeError, 'FILE_SET_INVALID'):
            self.build()
        (self.base/'unknown.py').unlink()
        (self.base/'source_policy.py').unlink()
        with self.assertRaisesRegex(RuntimeError, 'FILE_SET_INVALID'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_relocated_or_already_patched_inputs_are_rejected(self):
        path = self.sources['master_card.py']
        original = path.read_text()
        for changed in (original.replace('/home/Carix', str(self.root)), original+'\n# altered\n'):
            path.write_text(changed)
            with self.assertRaisesRegex(assembler.CandidateError, 'INPUT_HASH_MISMATCH'):
                self.build()
        self.assertFalse(self.output.exists())

    def test_pinned_helper_change_is_rejected(self):
        pins = dict(assembler.HELPER_PINS, **{'prepare_candidate.py': '0'*64})
        with patch.object(assembler, 'HELPER_PINS', pins):
            with self.assertRaisesRegex(assembler.CandidateError, 'INPUT_HASH_MISMATCH'):
                self.build()

    def test_output_exists_and_overlap_never_overwrite(self):
        self.output.mkdir()
        sentinel = self.output/'owner-file'
        sentinel.write_text('preserve owner file')
        with self.assertRaisesRegex(assembler.CandidateError, 'OUTPUT_ALREADY_EXISTS'):
            self.build()
        self.assertEqual(sentinel.read_text(), 'preserve owner file')
        with self.assertRaisesRegex(assembler.CandidateError, 'INPUT_OUTPUT_OVERLAP'):
            assembler.prepare(self.base, self.sources, self.base/'nested-output')

    def test_symlink_source_and_output_rejected(self):
        source = self.sources['db.py']
        saved = source.with_suffix('.saved')
        source.rename(saved)
        source.symlink_to(saved)
        with self.assertRaisesRegex(assembler.CandidateError, 'SYMLINK_FORBIDDEN'):
            self.build()
        source.unlink(); saved.rename(source)
        self.output.symlink_to(self.root/'elsewhere')
        with self.assertRaisesRegex(assembler.CandidateError, 'SYMLINK_FORBIDDEN'):
            self.build()

    def test_manifest_is_last_and_incomplete_output_is_not_ready(self):
        actual_link = os.link
        linked = []
        def link(source, target, *args, **kwargs):
            if target == 'manifest.json':
                self.assertEqual(set(linked), set(assembler.COMPLETE_FILES))
                with self.assertRaisesRegex(assembler.CandidateError, 'FILE_SET_INVALID'):
                    assembler.verify_candidate(self.output)
            result = actual_link(source, target, *args, **kwargs)
            linked.append(target)
            return result
        with patch.object(assembler.os, 'link', side_effect=link):
            self.build()
        self.assertEqual(linked[-1], 'manifest.json')

    def test_write_failure_cleans_only_owned_unfinished_output(self):
        actual_link = os.link
        count = 0
        def link(*args, **kwargs):
            nonlocal count
            count += 1
            if count == 4:
                raise OSError(errno.EIO, 'injected write failure')
            return actual_link(*args, **kwargs)
        with patch.object(assembler.os, 'link', side_effect=link):
            with self.assertRaises(OSError):
                self.build()
        self.assertFalse(self.output.exists())
        self.assertEqual(len(list(self.base.glob('*.py'))), 10)

    def test_input_drift_before_commit_creates_no_ready_output(self):
        actual = assembler._recheck
        def recheck(inputs):
            self.sources['db.py'].write_text(self.sources['db.py'].read_text()+'\n# concurrent edit\n')
            return actual(inputs)
        with patch.object(assembler, '_recheck', side_effect=recheck):
            with self.assertRaisesRegex(assembler.CandidateError, 'INPUT_HASH_MISMATCH'):
                self.build()
        self.assertFalse(self.output.exists())

    def test_input_drift_after_commit_invalidates_owned_ready_marker(self):
        actual = assembler._recheck
        count = 0
        def recheck(inputs):
            nonlocal count
            count += 1
            if count == 3:
                self.sources['db.py'].write_text(self.sources['db.py'].read_text()+'\n# concurrent edit\n')
            return actual(inputs)
        with patch.object(assembler, '_recheck', side_effect=recheck):
            with self.assertRaisesRegex(assembler.CandidateError, 'INPUT_HASH_MISMATCH'):
                self.build()
        self.assertTrue(self.output.is_dir())
        self.assertFalse((self.output/'manifest.json').exists())
        with self.assertRaisesRegex(assembler.CandidateError, 'FILE_SET_INVALID'):
            assembler.verify_candidate(self.output)

    def test_verifier_rejects_missing_unexpected_tampered_files_and_provenance(self):
        self.build()
        path = self.output/'car_number_allocator.py'
        old = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(assembler.CandidateError, 'FILE_SET_INVALID'):
            assembler.verify_candidate(self.output)
        path.write_bytes(old+b'\n# tampered\n')
        with self.assertRaisesRegex(assembler.CandidateError, 'HASH_MISMATCH'):
            assembler.verify_candidate(self.output)
        path.write_bytes(old)
        (self.output/'unexpected.py').write_text('pass\n')
        with self.assertRaisesRegex(assembler.CandidateError, 'FILE_SET_INVALID'):
            assembler.verify_candidate(self.output)
        (self.output/'unexpected.py').unlink()
        manifest = json.loads((self.output/'manifest.json').read_text())
        manifest['files']['db.py']['before_sha256'] = '0'*64
        (self.output/'manifest.json').write_text(json.dumps(manifest))
        with self.assertRaisesRegex(assembler.CandidateError, 'PROVENANCE_INVALID'):
            assembler.verify_candidate(self.output)
        manifest['files'] = assembler._expected_files()
        for key, value in (('overall_gate_b', 'PASS'), ('production_changed', True),
                           ('unreviewed_release_permission', True), ('limitations', [])):
            changed = dict(manifest, **{key: value})
            (self.output/'manifest.json').write_text(json.dumps(changed))
            with self.assertRaisesRegex(assembler.CandidateError, 'PROVENANCE_INVALID'):
                assembler.verify_candidate(self.output)


if __name__ == '__main__':
    unittest.main()
