#!/usr/bin/env python3
"""One-line approved-host correction, checked with the real guard on the real UA-0021 page."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_spec  # noqa: E402
import candidate_builder  # noqa: E402
import deployment_remote as remote  # noqa: E402

PROBE = HERE.parent / 'seo_source_probe_20261012_r2' / 'sanitized_sources.txt'
PAGES = HERE.parent / 'seo_source_probe_20261012' / 'public_pages.json'


def exported_spec():
    """The probe export of ua_additional_spec.py (one URL and one credential-like line masked)."""
    text = PROBE.read_text(encoding='utf-8').split('# ===== ua_additional_spec.py =====\n', 1)[1]
    lines = text.split('\n# ===== ua_delivery_status.py =====\n', 1)[0].rstrip('\n').split('\n')
    # The masked line was a loop body: keep the export compilable with an indented no-op.
    for i, line in enumerate(lines):
        if line == '[REDACTED]':
            lines[i] = ' ' * (len(lines[i - 1]) - len(lines[i - 1].lstrip()) + 4) + 'pass'
    return ('\n'.join(lines) + '\n').encode()


def guard(source):
    """_ua115_external_hosts and _UA115_APPROVED_HOSTS from the given ua_additional_spec source."""
    text = source.decode('utf-8')
    block = text[text.index('# >>> UA115 NO PUBLIC VIN ADS'):]
    tree = ast.parse(block.split('\n_UA115_MIN_SPEC_ROWS', 1)[0].split('\n', 2)[2] + '\n')
    hosts = next(node for node in tree.body if isinstance(node, ast.Assign))
    function = next(node for node in ast.parse(block).body
                    if isinstance(node, ast.FunctionDef) and node.name == '_ua115_external_hosts')
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / 'ua115_guard.py'
        path.write_text('import re\n\n' + ast.get_source_segment(block, function) + '\n', encoding='utf-8')
        spec = importlib.util.spec_from_file_location('ua115_guard', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module._ua115_external_hosts, ast.literal_eval(hosts.value)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.source = exported_spec()
        self.digest = hashlib.sha256(self.source).hexdigest()

    def test_only_the_host_line_changes(self):
        result = build_spec.build(self.source, expected=self.digest).decode()
        before, after = self.source.decode().splitlines(), result.splitlines()
        self.assertEqual(len(before), len(after))
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(changed, [(build_spec.OLD.rstrip('\n'), build_spec.NEW.rstrip('\n'))])

    def test_real_guard_rejects_ua0021_before_and_accepts_after(self):
        page = json.loads(PAGES.read_text(encoding='utf-8'))['/video/UA-0021.html']['body']
        external_hosts, old_hosts = guard(self.source)
        _, new_hosts = guard(build_spec.build(self.source, expected=self.digest))
        self.assertEqual(external_hosts(page) - old_hosts, {'www.searates.com'})
        self.assertEqual(external_hosts(page) - new_hosts, set())
        self.assertEqual(new_hosts - old_hosts, {'www.searates.com'})

    def test_refuses_other_inputs(self):
        with self.assertRaises(build_spec.BuildError):
            build_spec.build(self.source)  # the masked export is not the installed file
        changed = self.source.replace(build_spec.OLD.encode(), b'    "maps.app.goo.gl",\n')
        with self.assertRaises(build_spec.BuildError):
            build_spec.build(changed, expected=hashlib.sha256(changed).hexdigest())
        with self.assertRaises(ValueError):
            candidate_builder.build({'ua_additional_spec.py': self.source}, {})

    def test_pins_installed_file_and_no_new_modules(self):
        self.assertEqual(candidate_builder.SOURCE_SHA256,
                         {'ua_additional_spec.py': '6d2ab7b2bace29b8c0be58a6668264e695fd24f9e5e8f3ed6406da41ea45c672'})
        self.assertEqual(remote.NEW_MODULES, ())


if __name__ == '__main__':
    unittest.main()
