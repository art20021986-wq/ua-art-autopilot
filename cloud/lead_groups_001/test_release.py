"""The LEAD-GROUPS candidate is built only from the exact installed module versions (kept in the earlier packages)."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402

INSTALLED = {'ua_lead_desk.py': 'lead_folders_002', 'ua_lead_desk_view.py': 'lead_folders_002'}


def installed(name):
    return (HERE.parent / INSTALLED.get(name, 'lead_folders_001') / name).read_bytes()


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.source = {name: installed(name) for name in candidate_builder.SOURCE_FILES}
        self.dependencies = {name: installed(name) for name in candidate_builder.DEPENDENCY_SHA256}

    def test_builds_the_five_modules(self):
        result = candidate_builder.build(self.source, self.dependencies)
        self.assertEqual(sorted(result), sorted(candidate_builder.SOURCE_FILES))
        for name, value in result.items():
            compile(value, name, 'exec')
            self.assertNotEqual(value, self.source[name])

    def test_other_installed_version_stops(self):
        for name in candidate_builder.SOURCE_FILES + tuple(candidate_builder.DEPENDENCY_SHA256):
            changed = dict(self.source, **self.dependencies)
            changed[name] = changed[name] + b'\n'
            with self.assertRaisesRegex(ValueError, 'INPUT_HASH:' + name):
                candidate_builder.build({k: changed[k] for k in self.source}, {k: changed[k] for k in self.dependencies})


if __name__ == '__main__':
    unittest.main()
