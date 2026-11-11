#!/usr/bin/env python3
from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import autoria_click  # noqa: E402
import candidate_builder  # noqa: E402
import edit_home  # noqa: E402
import reviews_block  # noqa: E402
import reviews_data  # noqa: E402
import stats_loader  # noqa: E402
from release_constants import HOME  # noqa: E402

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
        self.assertEqual(text.count(edit_home.CHECK), 1)  # the reviews figure
        self.assertEqual(text.count('src="%s"' % reviews_block.LOGO), 2)  # button and badge
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
            self.assertIn('>%s</b>' % number, block)
            self.assertIn('data-ru="%s" data-uk="%s" data-ka="%s"' % (ru, uk, ka), block)
        for author, date, stars, text in reviews_data.REVIEWS:
            self.assertIn('«%s»' % text, block)
            self.assertIn('%s · %s' % (author, date), block)
        link = 'href="%s" target="_blank" rel="noopener noreferrer" data-autoria=' % reviews_data.DEALER_URL
        self.assertEqual(block.count(link + '"reviews_block"'), 1)
        self.assertEqual(reviews_block.badge().count(link + '"footer_badge"'), 1)
        self.assertEqual(block.count(autoria_click.SCRIPT), 1)
        self.assertTrue(block.endswith(autoria_click.SCRIPT + stats_loader.SCRIPT + '</section>'))
        self.assertIn('Перевірте нас на AUTO.RIA', block)
        self.assertIn('Проверьте нас на AUTO.RIA', block)
        self.assertEqual(block.count('<img class="ua-autoria-mark" src="/video/brand/autoria-logo.svg" alt="AUTO.RIA" '
                                     'width="101" height="30"'), 1)
        self.assertEqual(reviews_block.badge().count('<img class="ua-autoria-mark" src="/video/brand/autoria-logo.svg" '
                                                     'alt="AUTO.RIA" width="88" height="26"'), 1)

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
        self.assertEqual(candidate_builder.build({HOME: PAGE}, {}), {HOME: edit_home.build(PAGE)})

    def test_official_logo_in_site_design(self):
        css = reviews_block.CSS
        for absent in ('Roboto', '@font-face', '#fff', 'url('):
            self.assertNotIn(absent, css)
        self.assertEqual(css.count('border:1px solid var(--gold)'), 2)  # button and badge
        self.assertNotIn('>AUTO.RIA</span>', reviews_block.block() + reviews_block.badge())


class StatsLoaderTests(unittest.TestCase):
    def test_each_figure_carries_its_id_and_the_written_number(self):
        block = reviews_block.block()
        for name, (number, ru, uk, ka) in zip(('years', 'sold', 'reviews'), reviews_data.STATS):
            self.assertIn('<b id="ua-autoria-%s">%s</b><span data-ru="%s"' % (name, number, ru), block)
        self.assertEqual(block.count('<b id='), 3)
        self.assertEqual(reviews_data.FIGURES, stats_loader.FIELDS)

    def test_script_reads_only_our_file_and_keeps_the_numbers_otherwise(self):
        script = stats_loader.SCRIPT
        self.assertIn("fetch('/video/brand/autoria-sold.json',{cache:'no-cache'})", script)
        self.assertIn("var ok={years:/^[1-9][0-9]?\\+?$/,sold:/^[1-9][0-9]{0,5}$/,reviews:/^[1-9][0-9]{0,5}$/}", script)
        self.assertIn("document.getElementById('ua-autoria-'+k)", script)
        self.assertIn('.catch(function(){})', script)
        self.assertNotIn('innerHTML', script)
        self.assertNotIn('</', script[len('<script>'):-len('</script>')])  # cannot end the block early


if __name__ == '__main__':
    unittest.main()
