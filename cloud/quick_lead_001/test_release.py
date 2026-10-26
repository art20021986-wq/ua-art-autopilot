#!/usr/bin/env python3
"""Release-specific checks: exact installed inputs and the planned files only."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import candidate_builder
import edit_intake

HERE = Path(__file__).resolve().parent
# Where each installed module was last released (its plan holds the live hash).
PREVIOUS = {'ua_seo_landings.py': 'seo_landings_002', 'ua_seo_order_models.py': 'seo_models_001',
            'ua_seo_index.py': 'ga4_tag_001', 'ua_google_tag.py': 'ga4_tag_001',
            'ua_google_sitemap.py': 'gsc_growth_001', 'ua_seo_schema.py': 'ai_search_001',
            'ua_indexnow.py': 'ai_search_001'}
# The order package was never released from this repository: its live hashes come from the read-only probe.
PROBE = json.loads((HERE.parent/'order_intake_probe_001/20261026-R4.json').read_text())


def probe_sha(relative):
    return PROBE['source_hits']['/home/Carix/' + relative]['sha256']


def installed():
    """Exact live bytes where the repository has them (released modules, contract.py and crm.py)."""
    value = {name: (HERE.parent/folder/name).read_bytes() for name, folder in PREVIOUS.items()}
    for name in edit_intake.EDITS:
        value[name] = PROBE['package_sources'][name.split('/')[1]].encode() + b'\n'
    return value


class ReleaseTests(unittest.TestCase):
    def test_pins_match_the_live_files(self):
        for name, digest in {**candidate_builder.SOURCE_SHA256, **candidate_builder.DEPENDENCY_SHA256}.items():
            if name.startswith('ua_order/'):
                self.assertEqual(probe_sha(name), digest, name)
            else:
                plan = json.loads((HERE.parent/PREVIOUS[name]/'deployment_plan.json').read_text())
                self.assertEqual(plan['files'][name]['after'], digest, name)
        for name, value in installed().items():
            self.assertEqual(hashlib.sha256(value).hexdigest(),
                             {**candidate_builder.SOURCE_SHA256, **candidate_builder.DEPENDENCY_SHA256}[name], name)

    def build(self, source):
        # web/service/repository/preferences are only pinned (their full bytes are not in the repository).
        unavailable = {name: hashlib.sha256(b'live ' + name.encode()).hexdigest()
                       for name in candidate_builder.DEPENDENCY_SHA256 if name not in source}
        dependencies = {name: b'live ' + name.encode() for name in unavailable}
        with patch.dict(candidate_builder.DEPENDENCY_SHA256, unavailable):
            return candidate_builder.build(source, dependencies)

    def test_planned_files(self):
        result = self.build(installed())
        self.assertEqual(sorted(result), ['ua_order/contract.py', 'ua_order/crm.py', 'ua_order/quick.py',
                                          'ua_seo_landings.py', 'ua_seo_quick_form.py',
                                          'video/order/quick-lead.css', 'video/order/quick-lead.js'])
        for name, value in result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')

    def test_builder_refuses_unexpected_inputs(self):
        with self.assertRaises(ValueError):
            self.build({**installed(), 'ua_order/crm.py': b'other'})


if __name__ == '__main__':
    unittest.main()
