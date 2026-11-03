#!/usr/bin/env python3
"""The guard edit on the UA115 block as FINANCE-PROBE-20261103 read it (lines 761-768 of the live file)."""
import unittest

import candidate_builder
import edit_spec

LIVE = '''# >>> UA115 NO PUBLIC VIN ADS
_UA115_BASE_INJECT_PUBLIC_SPEC = inject_public_spec
_UA115_APPROVED_HOSTS = {
    "www.uaart.com.ua", "uaart.com.ua", "wa.me", "t.me", "telegram.org",
    "maps.app.goo.gl", "ecomm.one-line.com", "www.searates.com", "schema.org", "www.w3.org",
}
_UA115_MIN_SPEC_ROWS = 10
'''


class ReleaseTests(unittest.TestCase):
    def test_only_the_google_tag_host_is_added(self):
        result = candidate_builder.build({edit_spec.NAME: LIVE.encode()}, {})
        text = result[edit_spec.NAME].decode()
        self.assertEqual(edit_spec.approved_hosts(text) - edit_spec.approved_hosts(LIVE), {'www.googletagmanager.com'})
        self.assertEqual(text.replace(edit_spec.NEW, edit_spec.OLD), LIVE)

    def test_applied_edit_is_refused(self):
        once = edit_spec.build(edit_spec.NAME, LIVE.encode())
        with self.assertRaisesRegex(ValueError, 'SPEC_FRAGMENT'):
            edit_spec.build(edit_spec.NAME, once)


if __name__ == '__main__':
    unittest.main()
