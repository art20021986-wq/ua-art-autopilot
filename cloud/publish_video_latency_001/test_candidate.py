"""Static regression for exact deletion; live-source execution is local evidence."""
import ast
from pathlib import Path
import unittest
from candidate_builder import build, patch_publisher

HOOK = (Path(__file__).parent / 'legacy_hook.py').read_text()
BASE = '''
def _zapisat_atomarno(put, tekst):
    validate(tekst)
    atomic_write(put, tekst)
'''

class CandidateTests(unittest.TestCase):
    def test_only_obsolete_wrapper_is_removed(self):
        source = BASE + HOOK + '\n# preserved end\n'
        result = patch_publisher(source)
        self.assertEqual(result, BASE + '\n# preserved end\n')
        self.assertEqual(ast.dump(ast.parse(result)), ast.dump(ast.parse(BASE)))

    def test_missing_or_duplicated_hook_is_rejected(self):
        for source in (BASE, BASE + HOOK + HOOK):
            with self.assertRaises(ValueError):
                patch_publisher(source)

    def test_unrecognized_source_set_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SOURCE_OR_DEPENDENCY_SET'):
            build({}, {})

    def test_changed_source_or_dependency_is_rejected(self):
        from candidate_builder import SOURCE_SHA256, DEPENDENCY_SHA256
        with self.assertRaisesRegex(ValueError, 'SOURCE_OR_DEPENDENCY_CHANGED'):
            build({name:b'changed' for name in SOURCE_SHA256},
                  {name:b'changed' for name in DEPENDENCY_SHA256})

if __name__ == '__main__':
    unittest.main()
