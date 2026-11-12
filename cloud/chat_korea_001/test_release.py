"""The CHAT-KOREA candidate from the live Korea page."""
import hashlib
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402
import ua_chat_button  # noqa: E402

LIVE_MODULE = HERE.parent / 'chat_button_001' / 'ua_chat_button.py'


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.page = (HERE / 'fixtures' / 'korea_live.html').read_text('utf-8')
        self.module = (HERE / cb.MODULE).read_bytes()

    def build(self, page):
        return cb.build({cb.PAGE: page.encode('utf-8')}, {cb.MODULE: self.module})[cb.PAGE].decode('utf-8')

    def test_style_added_once_before_body_end(self):
        new = self.build(self.page)
        self.assertEqual(new.count(ua_chat_button.MARK), 1)
        self.assertEqual(new.replace(ua_chat_button.HTML, '', 1), self.page)
        self.assertLess(new.index(ua_chat_button.END), new.rindex('</body>'))
        self.assertIn('class="mcf-chat floating-chat" href="https://wa.me/380992222002"', new)

    def test_same_style_as_the_installed_release(self):
        self.assertEqual(self.module, LIVE_MODULE.read_bytes())

    def test_installed_page_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'CHAT_KOREA_PAGE_UNEXPECTED'):
            cb.apply(cb.apply(self.page))

    def test_other_live_module_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'CHAT_KOREA_LIVE_MODULE_DIFFERS'):
            cb.build({cb.PAGE: self.page.encode('utf-8')}, {cb.MODULE: self.module + b'\n'})
        self.assertEqual(cb.DEPENDENCY_SHA256[cb.MODULE], hashlib.sha256(self.module).hexdigest())


if __name__ == '__main__':
    unittest.main()
