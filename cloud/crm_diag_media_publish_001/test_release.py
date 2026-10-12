#!/usr/bin/env python3
"""Release-specific checks: exact input, new module shipped as is, no catalog repair."""
import unittest

import candidate_builder
import deployment_remote as remote
from release_constants import NEW_MODULE


class ReleaseTests(unittest.TestCase):
    def test_builder_refuses_unexpected_inputs(self):
        with self.assertRaises(ValueError):
            candidate_builder.build({'ua_crm_public_sync.py': b'other'}, {})

    def test_builder_pins_installed_sync(self):
        self.assertEqual(candidate_builder.SOURCE_SHA256['ua_crm_public_sync.py'],
                         '8c65eeb598c15007f489e2eaa0453362c97b9c426a3f67cf02c6a09a0d37015f')

    def test_new_module_shipped_from_package(self):
        self.assertEqual(NEW_MODULE, 'ua_diag_files.py')
        self.assertTrue((candidate_builder.HERE / NEW_MODULE).is_file())

    def test_no_catalog_repair_mode(self):
        self.assertFalse(hasattr(remote, 'repair_catalog'))


if __name__ == '__main__':
    unittest.main()
