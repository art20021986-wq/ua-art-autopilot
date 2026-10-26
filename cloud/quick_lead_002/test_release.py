#!/usr/bin/env python3
"""Release-specific checks: exact installed inputs and the planned files only."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import candidate_builder
import test_order_offer

HERE = Path(__file__).resolve().parent
# Where each installed file was last released (its plan holds the live hash).
PREVIOUS = {'ua_order/quick.py': 'quick_lead_001', 'ua_seo_quick_form.py': 'quick_lead_001',
            'video/order/quick-lead.js': 'quick_lead_001', 'video/order/quick-lead.css': 'quick_lead_001',
            'ua_seo_landings.py': 'quick_lead_001', 'ua_order/contract.py': 'quick_lead_001',
            'ua_order/crm.py': 'quick_lead_001', 'video/podbor.html': 'podbor_model_001',
            'video/order/order.js': 'podbor_model_001', 'video/order/order-strings.json': 'podbor_form_001',
            'ua_seo_order_models.py': 'seo_models_001', 'ua_seo_index.py': 'ga4_tag_001',
            'ua_google_tag.py': 'ga4_tag_001', 'ua_google_sitemap.py': 'gsc_growth_001',
            'ua_seo_schema.py': 'ai_search_001', 'ua_indexnow.py': 'ai_search_001'}
PROBE = json.loads((HERE.parent/'order_intake_probe_001/20261026-R4.json').read_text())
PINS = {**candidate_builder.SOURCE_SHA256, **candidate_builder.DEPENDENCY_SHA256}


class ReleaseTests(unittest.TestCase):
    def test_pins_match_the_installed_releases(self):
        for name, digest in PINS.items():
            if name in PREVIOUS:
                plan = json.loads((HERE.parent/PREVIOUS[name]/'deployment_plan.json').read_text())
                self.assertEqual(plan['files'][name]['after'], digest, name)
            else:  # order package modules never released from here: the read-only probe
                self.assertEqual(PROBE['source_hits']['/home/Carix/' + name]['sha256'], digest, name)

    def build(self):
        source = test_order_offer.live_order_files()
        unavailable = {name: hashlib.sha256(b'live ' + name.encode()).hexdigest() for name in PINS if name not in source}
        dependencies = {name: b'live ' + name.encode() for name in unavailable}
        with patch.dict(candidate_builder.SOURCE_SHA256, {k: v for k, v in unavailable.items()
                                                          if k in candidate_builder.SOURCE_SHA256}), \
             patch.dict(candidate_builder.DEPENDENCY_SHA256, {k: v for k, v in unavailable.items()
                                                              if k in candidate_builder.DEPENDENCY_SHA256}):
            return candidate_builder.build(source, dependencies)

    def test_planned_files(self):
        result = self.build()
        self.assertEqual(sorted(result), ['ua_order/quick.py', 'ua_seo_quick_form.py', 'video/order/order-strings.json',
                                          'video/order/order.js', 'video/order/quick-lead.css',
                                          'video/order/quick-lead.js', 'video/podbor.html'])
        for name, value in result.items():
            if name.endswith('.py'):
                compile(value, name, 'exec')
        json.loads(result['video/order/order-strings.json'])


if __name__ == '__main__':
    unittest.main()
