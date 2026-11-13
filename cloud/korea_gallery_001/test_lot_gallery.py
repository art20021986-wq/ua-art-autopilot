import pathlib
import re
import unittest

import lot_gallery_page
import lot_gallery_script
import lot_gallery_style

HERE = pathlib.Path(__file__).resolve().parent
LIVE = (HERE / 'fixtures' / 'korea_live.html').read_bytes()  # korea.html as KOREA-ENGINE-INSTALL leaves it


class StylesTest(unittest.TestCase):
    def test_catalogue_styles_byte_for_byte(self):
        """The viewer looks like the catalogue car cards: its styles are the installed catalogue gallery's own."""
        catalogue = (HERE.parent / 'media_gallery_final_001' / 'ua_media_styles.py').read_bytes()
        self.assertEqual((HERE / 'ua_media_styles.py').read_bytes(), catalogue)
        self.assertTrue(lot_gallery_style.CSS.startswith(lot_gallery_style.CATALOGUE))

    def test_lot_rules_are_scoped(self):
        for rule in re.findall(r'([^{}]+)\{', lot_gallery_style.LOT):
            for selector in rule.split(','):
                self.assertTrue(selector.startswith(('.kg-gallery', '.kg-frame')), selector)


class ScriptTest(unittest.TestCase):
    def test_accessible_controls(self):
        js = lot_gallery_script.JS
        for piece in ("role: 'tablist'", "role: 'tab'", "'aria-selected'", "role: 'status'", "'aria-live': 'polite'",
                      "previous.setAttribute('aria-label'", "next.setAttribute('aria-label'", "img.alt = title",
                      'ArrowRight', 'ArrowLeft', 'Home', 'End', "'pointerup'", "el('dialog', 'um-dialog')",
                      'dialog.showModal()', "expand.setAttribute('aria-label'", "close.setAttribute('aria-label'",
                      'opener.focus('):
            self.assertIn(piece, js)
        self.assertNotIn('</script', js)

    def test_three_languages(self):
        for lang in ('uk:', 'ru:', 'ka:'):
            self.assertIn(lang, lot_gallery_script.JS)


class PageTest(unittest.TestCase):
    def test_viewer_added_and_old_loader_removed(self):
        out = lot_gallery_page.build(LIVE).decode('utf-8')
        self.assertIn(lot_gallery_page.CHECK, out)
        self.assertNotIn('function gallery(l)', out)
        self.assertNotIn('gallery(l);', out)
        self.assertEqual(out.count('<!--%s-->' % lot_gallery_page.MARK), 1)
        self.assertLess(out.index(lot_gallery_page.CHECK), out.index('</body>'))
        rest = out.replace(lot_gallery_page.BLOCK, '').replace('scrollTop=0;if(', 'scrollTop=0;gallery(l);if(')
        rest = rest.replace('}function open(id){', '}' + lot_gallery_page.LOADER + 'function open(id){', 1)
        self.assertEqual(rest.encode('utf-8'), LIVE)  # only these edits

    def test_applied_once_and_unknown_page_refused(self):
        with self.assertRaises(ValueError):
            lot_gallery_page.build(lot_gallery_page.build(LIVE))
        with self.assertRaises(ValueError):
            lot_gallery_page.build(LIVE.replace(lot_gallery_page.CALL.encode('utf-8'), b''))


if __name__ == '__main__':
    unittest.main()
