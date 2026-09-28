import unittest
from unittest.mock import patch

import release_check


class ReleaseGuardTest(unittest.TestCase):
    def test_private_backup_cannot_target_public_or_arbitrary_directory(self):
        for output in ('/home/Carix/video/order_release_check_test',
                       '/tmp/order_release_check_test', '/home/Carix/other'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                release_check.run(output)

    def test_first_install_rehearsal_refuses_existing_feature_paths(self):
        for existing in ('/home/Carix/ua_order', '/home/Carix/order_requests', '/home/Carix/video/order'):
            with self.subTest(existing=existing):
                with patch.object(release_check.Path, 'exists', lambda path: str(path) == existing):
                    with self.assertRaisesRegex(ValueError, 'Existing feature paths'):
                        release_check.run('/home/Carix/order_release_check_test')


if __name__ == '__main__':
    unittest.main()
