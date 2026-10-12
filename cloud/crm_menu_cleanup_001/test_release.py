#!/usr/bin/env python3
"""Release-specific checks: exact inputs and one-file plan without site writes."""
import hashlib
import unittest

import candidate_builder
import deployment_remote as remote


class ReleaseTests(unittest.TestCase):
    def test_builder_refuses_unexpected_inputs(self):
        with self.assertRaises(ValueError):
            candidate_builder.build({'cars_ui.py': b'other'}, {})

    def test_builder_pins_installed_sources(self):
        self.assertEqual(candidate_builder.SOURCE_SHA256['cars_ui.py'],
                         'ce0d132710bfc1e2371758bda0d5159a6756bd82305843c109edb91e522e939b')
        self.assertEqual(candidate_builder.DEPENDENCY_SHA256, {})

    def test_no_catalog_repair_mode(self):
        self.assertFalse(hasattr(remote, 'repair_catalog'))


if __name__ == '__main__':
    unittest.main()
