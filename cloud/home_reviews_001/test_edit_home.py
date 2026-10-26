#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import autoria_click  # noqa: E402
import autoria_logo  # noqa: E402
import candidate_builder  # noqa: E402
import edit_home  # noqa: E402
import reviews_block  # noqa: E402
import reviews_data  # noqa: E402
from release_constants import HOME, LOGO  # noqa: E402

STEPS = '<section class="ua-how section-frame"><h2>5 кроків</h2><ol><li>1</li></ol></section>'
PAGE = ('<html><head><title>x</title></head><body><main>%s<section id="stages"></section></main>'
        '<footer class="site-footer"><div class="footer-meta"><span>Київ</span></div>'
        '<div class="signature">BA</div></footer></body></html>' % STEPS).encode()


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.open = []

    def handle_starttag(self, tag, attrs):
        if tag not in ('img', 'meta', 'br'):
            self.open.append(tag)

    def handle_endtag(self, tag):
        assert self.open.pop() == tag, tag


class EditHomeTests(unittest.TestCase):
    def setUp(self):
        self.result = edit_home.build(PAGE).decode()

    def test_block_after_steps_badge_before_signature_css_in_head(self):
        text = self.result
        self.assertEqual(text.count(edit_home.CHECK), 1)
        css = '<style id="%s">' % reviews_block.MARK
        self.assertLess(text.index(STEPS), text.index('class="ua-reviews'))
        self.assertLess(text.index('class="ua-reviews'), text.index('id="stages"'))
        self.assertLess(text.index('class="ua-autoria-badge"'), text.index('<div class="signature"'))
        self.assertGreater(text.index('class="ua-autoria-badge"'), text.index('<footer'))
        self.assertLess(text.index(css), text.index('</head>'))

    def test_only_insertions(self):
        stripped = (self.result.replace(reviews_block.block(), '').replace(reviews_block.badge(), '')
                    .replace(reviews_block.CSS, ''))
        self.assertEqual(stripped.encode(), PAGE)

    def test_markup_is_balanced(self):
        parser = Tags()
        parser.feed(reviews_block.block() + reviews_block.badge())
        self.assertEqual(parser.open, [])

    def test_content(self):
        block = reviews_block.block()
        for number, ru, uk, ka in reviews_data.STATS:
            self.assertIn('<b>%s</b>' % number, block)
            self.assertIn('data-ru="%s" data-uk="%s" data-ka="%s"' % (ru, uk, ka), block)
        for author, date, stars, text in reviews_data.REVIEWS:
            self.assertIn('«%s»' % text, block)
            self.assertIn('%s · %s' % (author, date), block)
        link = 'href="%s" target="_blank" rel="noopener noreferrer" data-autoria=' % reviews_data.DEALER_URL
        self.assertEqual(block.count(link + '"reviews_block"'), 1)
        self.assertEqual(reviews_block.badge().count(link + '"footer_badge"'), 1)
        self.assertEqual(block.count(autoria_click.SCRIPT), 1)
        self.assertTrue(block.endswith(autoria_click.SCRIPT + '</section>'))
        self.assertIn('Перевірте нас на AUTO.RIA', block)
        self.assertIn('Проверьте нас на AUTO.RIA', block)
        self.assertIn('src="/%s"' % LOGO, block)

    def test_every_translated_node_has_georgian(self):
        for markup in (reviews_block.block(), reviews_block.badge()):
            self.assertEqual(markup.count('data-ru='), markup.count('data-ka='))

    def test_click_event(self):
        script = autoria_click.SCRIPT
        self.assertIn("closest('a[data-autoria]')", script)
        self.assertIn("gtag('event','autoria_click',{placement:a.getAttribute('data-autoria')})", script)
        self.assertIn("typeof gtag==='function'", script)
        self.assertIn(edit_home.CHECK, self.result)

    def test_refresh_replaces_installed_fragments(self):
        old = (PAGE.decode().replace(STEPS, STEPS + '<section class="ua-reviews section-frame" id="vidguky"><p>old</p></section>')
               .replace('<div class="signature"', '<a class="ua-autoria-badge" href="x"><span>old</span></a><div class="signature"')
               .replace('</head>', '<style id="%s">.old{}</style></head>' % reviews_block.MARK))
        self.assertEqual(edit_home.build(old.encode()).decode(), self.result)
        self.assertEqual(edit_home.build(self.result.encode()).decode(), self.result)

    def test_translated_nodes_hold_text_only(self):
        # The home language switch replaces textContent of every [data-ru] node.
        for markup in (reviews_block.block(), reviews_block.badge()):
            for part in markup.split('data-ru=')[1:]:
                inner = part.split('>', 1)[1]
                self.assertTrue(inner.split('</', 1)[0].find('<') == -1)

    def test_refuses_changed_page(self):
        with self.assertRaises(ValueError):
            edit_home.build(self.result.replace('class="ua-autoria-badge"', 'class="other"').encode())
        with self.assertRaises(ValueError):
            edit_home.build(PAGE.replace(b'ua-how', b'other'))
        with self.assertRaises(ValueError):
            edit_home.build(PAGE.replace(b'</footer>', b'<div class="signature"></div></footer>'))

    def test_candidate(self):
        result = candidate_builder.build({HOME: PAGE}, {})
        self.assertEqual(sorted(result), sorted([HOME, LOGO]))
        self.assertEqual(result[LOGO], autoria_logo.SVG.encode())
        self.assertTrue(result[LOGO].startswith(b'<svg') and result[LOGO].endswith(b'</svg>'))
        live = candidate_builder.build({HOME: result[HOME], LOGO: result[LOGO]}, {})
        self.assertEqual(live, {HOME: result[HOME]})


if __name__ == '__main__':
    unittest.main()
