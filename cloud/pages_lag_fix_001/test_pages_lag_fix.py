#!/usr/bin/env python3
"""PAGES-LAG-FIX-001: the edits on the live sources (fixtures are byte-exact copies read by PAGES-LAG-PROBE), the
preview check run here with this Python, and the rebuild retry of the candidate self-check."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402
import edit_samokontrol  # noqa: E402
import edit_usercustomize  # noqa: E402

LIVE = {edit_samokontrol.NAME: (HERE / 'fixtures/samokontrol.txt').read_bytes(),
        edit_usercustomize.NAME: (HERE / 'fixtures/usercustomize_310.txt').read_bytes()}


class EditTests(unittest.TestCase):
    def test_candidate_changes_only_the_two_blocks(self):
        result = candidate_builder.build(LIVE, {})
        for edit in candidate_builder.EDITS:
            before, after = LIVE[edit.NAME].decode(), result[edit.NAME].decode()
            compile(after, edit.NAME, 'exec')
            self.assertEqual(after, before.replace(edit.OLD, edit.NEW))
            self.assertEqual(after.count('PAGES-LAG-FIX-001'), 1)
            with self.assertRaises(ValueError):
                edit.build(result[edit.NAME])

    def test_other_usercustomize_blocks_untouched(self):
        after = candidate_builder.build(LIVE, {})[edit_usercustomize.NAME].decode()
        for line in ('import odna_karta; odna_karta.start()', 'import vitrina; vitrina.start()', 'import avtoperedacha',
                     'import video_sinhron', 'import svezhiy_hesh', 'import lock4_zhurnal'):
            self.assertEqual(after.count(line), 1, line)

    def test_changed_source_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'EDIT_ANCHOR'):
            edit_samokontrol.build(LIVE[edit_samokontrol.NAME].replace(b'timeout=600', b'timeout=900'))


class PreviewCheckTests(unittest.TestCase):
    def test_smoke_script_with_this_python(self):
        result = candidate_builder.build(LIVE, {})
        with tempfile.TemporaryDirectory() as folder:
            after = Path(folder) / 'after'
            for name, value in result.items():
                (after / name).parent.mkdir(parents=True, exist_ok=True)
                (after / name).write_bytes(value)
            out = subprocess.run([sys.executable, '-B', '-c', remote.SMOKE, str(after)], capture_output=True, text=True,
                                 timeout=120, check=True).stdout
        value = json.loads(out.strip().splitlines()[-1])
        self.assertEqual({k: value[k] for k in remote.EXPECTED}, remote.EXPECTED)


class RetryTests(unittest.TestCase):
    def module(self, folder, script):
        source = candidate_builder.build(LIVE, {})[edit_samokontrol.NAME].decode()
        source = source.replace('BAZA = "/home/Carix"', 'BAZA = %r' % str(folder))
        source = source.replace('\ntry:\n    start()\nexcept Exception:\n    pass', '\n')
        path = Path(folder) / 'samokontrol_candidate.py'
        path.write_text(source, encoding='utf-8')
        (Path(folder) / 'stranica.py').write_text(script, encoding='utf-8')
        spec = importlib.util.spec_from_file_location('samokontrol_candidate', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_failed_build_logs_tail_and_retries_once(self):
        with tempfile.TemporaryDirectory() as folder:
            module = self.module(folder, 'import sys\nsys.stderr.write("BOOM database is locked")\nsys.exit(1)\n')
            with patch.object(module.time, 'sleep') as pause:
                self.assertFalse(module.sobrat())
            log = (Path(folder) / 'samokontrol_log.txt').read_text(encoding='utf-8')
            self.assertEqual(log.count('код 1'), 2)
            self.assertIn('ошибка сборки, попытка 1: BOOM database is locked', log)
            self.assertIn('ошибка сборки, попытка 2', log)
            pause.assert_called_once_with(60)

    def test_second_try_success_is_success(self):
        with tempfile.TemporaryDirectory() as folder:
            marker = Path(folder) / 'tried'
            module = self.module(folder, 'import pathlib, sys\np = pathlib.Path(%r)\n'
                                         'sys.exit(0 if p.exists() else (p.write_text("1") and 1))\n' % str(marker))
            with patch.object(module.time, 'sleep'):
                self.assertTrue(module.sobrat())

    def test_first_try_success_no_pause(self):
        with tempfile.TemporaryDirectory() as folder:
            module = self.module(folder, 'pass\n')
            with patch.object(module.time, 'sleep') as pause:
                self.assertTrue(module.sobrat())
            pause.assert_not_called()


if __name__ == '__main__':
    unittest.main()
