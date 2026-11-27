#!/usr/bin/env python3
"""SEARCH-HOME-001 B: the module on a copy of the live home page (after HOME-BLOCKS-001, 2026-11-27) and the candidate."""
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import release_constants  # noqa: E402
import ua_search_home  # noqa: E402

INJECT = (HERE/'fixtures/site_ge_inject_installed.txt').read_bytes()


def home():
    return (HERE/'fixtures/index_live.html').read_text(encoding='utf-8')


class ModuleTests(unittest.TestCase):
    def test_search_replaces_the_inside_of_the_auctions_section_only(self):
        before = home()
        page = ua_search_home.apply(before)
        self.assertEqual(page.count('<!--UA-SEARCH-HOME-V1-->'), 1)
        self.assertEqual(page.count('class="ua-kr-auc"'), 1)
        self.assertLess(page.index('class="ua-kr-auc"'), page.index('name="sh-country"'))
        self.assertLess(page.index('name="sh-country"'), page.index('id="ua-korea-ticker"'))
        self.assertNotIn('Авто з аукціонів Кореї — нові лоти щодня', page)
        self.assertIn('Пошук авто на аукціонах світу', page)
        start = before.index('<section class="ua-kr-auc">')
        self.assertEqual(page[:start], before[:start])  # everything before the section stays
        tail = before[before.index('</section>', start):]
        self.assertTrue(page.endswith(tail))  # and everything after it
        self.assertEqual(ua_search_home.apply(page), page)  # once

    def test_rollback_gives_the_section_back(self):
        page = ua_search_home.apply(home())
        self.assertEqual(ua_search_home.remove(page, home()), home())

    def test_page_without_the_section_is_unchanged(self):
        other = '<html><body><main id="main-content"><p>catalog</p></main></body></html>'
        self.assertEqual(ua_search_home.apply(other), other)

    def test_countries_as_the_row_below_and_links(self):
        block = ua_search_home.block()
        for key in ('all', 'korea', 'usa', 'japan', 'europe', 'china', 'canada', 'uae', 'georgia'):
            self.assertIn('value="%s"' % key, block)
        self.assertIn('data-href="usa.html"', block)
        self.assertIn('value="japan" data-href="japan.html"', block)  # JAPAN-LHD-001 installed its page
        self.assertIn("'#lots'", block)
        self.assertIn("['maker','model','year','usd']", block)
        # the counter and the models come from the small hourly summary, not the full lot lists
        self.assertIn('class="sh-today"', block)
        self.assertIn('/video/auctions/summary.json', block)
        self.assertNotIn('lots.json', block)
        self.assertNotIn('sh-found', block)
        for word in ('2mcars', 'vsbrothers', 'vs brothers'):
            self.assertNotIn(word, block.lower())


class SummaryTests(unittest.TestCase):
    def test_summary_counts_by_country_make_and_model(self):
        import json
        import ua_auction_summary as summary
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            (root/'video/korea').mkdir(parents=True)
            (root/'video/korea/lots.json').write_text(json.dumps({'lots': [
                {'maker': 'Kia', 'title': 'Kia K5'}, {'maker': 'Kia', 'title': 'Kia K5'},
                {'maker': 'Bmw', 'title': 'Bmw 520d'}]}), encoding='utf-8')
            (root/'video/japan').mkdir(parents=True)
            (root/'video/japan/lots.json').write_text('not json', encoding='utf-8')
            value = summary.build(root)
            summary.write(value, root)
            saved = json.loads((root/summary.TARGET).read_text(encoding='utf-8'))
        self.assertEqual(saved['total'], 3)
        self.assertEqual(sorted(saved['countries']), ['korea'])  # unreadable and missing lists are left out
        self.assertEqual(saved['countries']['korea']['makers']['kia'], {'name': 'Kia', 'total': 2, 'models': {'K5': 2}})


class CandidateTests(unittest.TestCase):
    def test_candidate_is_the_module_the_wrapper_and_the_home_page(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root)/'video').mkdir()
            (Path(root)/'video/index.html').write_text(home(), encoding='utf-8')
            names = candidate_builder.targets(root)
        self.assertEqual(names, ('site_ge_inject.py', 'video/index.html'))
        files = candidate_builder.build({'site_ge_inject.py': INJECT, 'video/index.html': home().encode('utf-8')}, {})
        self.assertEqual(set(files), {'ua_search_home.py', 'ua_auction_summary.py', 'site_ge_inject.py',
                                      'video/index.html'})
        inject = files['site_ge_inject.py'].decode('utf-8')
        self.assertTrue(inject.startswith(INJECT.decode('utf-8').rstrip('\n')))
        self.assertTrue(inject.rstrip().endswith('return ua_search_home.apply(_ua_search_home_base_inject(source))'))
        compile(inject, 'site_ge_inject.py', 'exec')
        self.assertIn('<!--UA-SEARCH-HOME-V1-->', files['video/index.html'].decode('utf-8'))

    def test_refuses_twice_and_without_home_blocks(self):
        files = candidate_builder.build({'site_ge_inject.py': INJECT, 'video/index.html': home().encode('utf-8')}, {})
        with self.assertRaises(ValueError):
            candidate_builder.edit('site_ge_inject.py', files['site_ge_inject.py'])
        with self.assertRaises(ValueError):
            candidate_builder.edit('site_ge_inject.py', b'def inject_html(source):\n    return source\n')

    def test_health_checks_name_only_pages_that_exist_before_the_install(self):
        for url in release_constants.HEALTH_CHECKS:
            self.assertTrue(url.startswith('https://www.uaart.com.ua/video/'))
            self.assertIn(url.rsplit('/', 1)[1], ('index.html', 'katalog.html', 'korea.html'))


if __name__ == '__main__':
    unittest.main()
