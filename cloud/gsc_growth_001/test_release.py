#!/usr/bin/env python3
"""Release-specific checks: exact installed inputs and the planned code files only."""
import hashlib
import json
from pathlib import Path
import unittest

import candidate_builder

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.parent / 'ai_search_001'


def installed():
    names = list(candidate_builder.SOURCE_SHA256) + list(candidate_builder.DEPENDENCY_SHA256)
    return {name: (PREVIOUS / name).read_bytes() for name in names}


class ReleaseTests(unittest.TestCase):
    def test_pins_match_the_installed_ai_search_release(self):
        plan = json.loads((PREVIOUS / 'deployment_plan.json').read_text())['files']
        for name, digest in {**candidate_builder.SOURCE_SHA256, **candidate_builder.DEPENDENCY_SHA256}.items():
            self.assertEqual(plan[name]['after'], digest)
            self.assertEqual(hashlib.sha256(installed()[name]).hexdigest(), digest)

    def test_builder_refuses_unexpected_inputs(self):
        with self.assertRaises(ValueError):
            candidate_builder.build({**installed(), 'ua_seo_index.py': b'other'}, {})

    def test_planned_files(self):
        result = candidate_builder.build(installed(), {})
        self.assertEqual(sorted(result), ['ua_google_sitemap.py', 'ua_seo_index.py', 'ua_seo_landings.py'])
        for name, value in result.items():
            compile(value, name, 'exec')


if __name__ == '__main__':
    unittest.main()
