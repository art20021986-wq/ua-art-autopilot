"""The KOREA-FLAG candidate from the home page and module as installed by KOREA-AUCTION-INSTALL-20261110-R3."""
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_korea_home  # noqa: E402

LIVE = (HERE / 'fixtures' / 'index_live.html').read_text()
# the module installed by KOREA-AUCTION-INSTALL-20261110-R3 (cloud/korea_auction_001 at that install)
INSTALLED_MODULE = (HERE / 'fixtures' / 'ua_korea_home_installed.txt').read_bytes()


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.home = ua_korea_home.apply(LIVE).replace(ua_korea_home.FLAG_TO, ua_korea_home.FLAG_FROM)  # as installed
        self.source = {'ua_korea_home.py': INSTALLED_MODULE, 'video/index.html': self.home.encode()}

    def test_only_the_flag_link_changes(self):
        self.assertIn(b'ua-korea-ticker', INSTALLED_MODULE)
        result = candidate_builder.build(self.source, {})
        new_home = result['video/index.html'].decode()
        self.assertEqual(new_home, ua_korea_home.apply(LIVE))
        self.assertEqual(new_home.replace(ua_korea_home.FLAG_TO, ua_korea_home.FLAG_FROM), self.home)
        compile(result['ua_korea_home.py'], 'ua_korea_home.py', 'exec')

    def test_second_build_refused(self):
        result = candidate_builder.build(self.source, {})
        with self.assertRaises(ValueError):
            candidate_builder.build(result, {})


if __name__ == '__main__':
    unittest.main()
