import hashlib
from pathlib import Path
import unittest

import audi_photo
import candidate_builder
import deployment_bootstrap
import edit_home
from release_constants import HOME, PHOTO

HERO = ('<section class="hero ua-order-first"><picture><source media="(max-width:700px)" '
        'srcset="/video/order/kia_k5_mobile.webp" type="image/webp"><img src="/video/order/kia_k5_desktop.webp" '
        'alt="Kia K5 — UA ART COMPANY, Київ" width="1400" height="868" fetchpriority="high" decoding="async">'
        '</picture><div class="ua-order-shade"></div><div class="ua-order-copy"><h1>Авто</h1></div></section>')
PAGE = ('<html><head><title>UA ART</title><style id="ua-home-layout-001">.x{}</style></head><body>%s'
        '<section class="ua-how section-frame"><picture><img src="/video/foto/UA-0001/001.jpg"></picture></section>'
        '</body></html>' % HERO)


class EditHomeTests(unittest.TestCase):
    def test_photo_is_owner_file_byte_for_byte(self):
        # Owner photo cropped around the car (x 338..2094), approved in chat 2026-10-27.
        self.assertEqual(hashlib.sha256(audi_photo.JPEG).hexdigest(), '849696a5ff0ebfd5e8cf101492ccb54fff39cc4bdeb69711b57206c1a52a9cec')

    def test_only_first_screen_picture_and_css_change(self):
        result = edit_home.build(PAGE.encode()).decode()
        self.assertNotIn('kia_k5', result)
        self.assertIn(edit_home.PICTURE_HTML, result)
        self.assertIn('/video/foto/UA-0001/001.jpg', result)
        self.assertEqual(result.count(edit_home.CSS), 1)
        self.assertLess(result.index(edit_home.CSS), result.index('</head>'))
        self.assertGreater(result.index(edit_home.CSS), result.index('ua-home-layout-001'))
        self.assertEqual(result.replace(edit_home.CSS, '').replace(edit_home.PICTURE_HTML, '<P>'),
                         PAGE.replace(HERO[HERO.index('<picture>'):HERO.index('</picture>') + 10], '<P>'))

    def test_photo_shown_whole(self):
        self.assertIn('object-fit:contain', edit_home.CSS)
        self.assertIn('aspect-ratio:1756/1190', edit_home.CSS)
        self.assertIn('width="1756" height="1190"', edit_home.PICTURE_HTML)

    def test_second_release_replaces_in_place(self):
        once = edit_home.build(PAGE.encode())
        self.assertEqual(edit_home.build(once), once)

    def test_unknown_layout_changes_nothing(self):
        for page in (PAGE.replace('ua-order-first', 'other'), PAGE.replace('</head>', ''),
                     PAGE.replace(HERO, HERO + HERO)):
            with self.assertRaises(ValueError):
                edit_home.build(page.encode())

    def test_candidate_has_page_and_photo(self):
        result = candidate_builder.build({HOME: PAGE.encode()}, {})
        self.assertEqual(set(result), {HOME, PHOTO})
        self.assertEqual(result[PHOTO], audi_photo.JPEG)
        self.assertIn(edit_home.CHECK.encode(), result[HOME])

    def test_every_package_file_fits_the_bootstrap_limit(self):
        for path in Path(__file__).resolve().parent.glob('*.py'):
            self.assertLessEqual(path.stat().st_size, deployment_bootstrap.ENTRY_LIMIT, path.name)


if __name__ == '__main__':
    unittest.main()
