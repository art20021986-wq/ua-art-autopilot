#!/usr/bin/env python3
"""HOME-BLOCKS-001: the module on a copy of the live home page (2026-11-27) and the candidate on the installed sources."""
import hashlib
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder  # noqa: E402
import ua_home_blocks  # noqa: E402

INJECT = (HERE/'fixtures/site_ge_inject.txt').read_text(encoding='utf-8')


def home():
    return (HERE/'fixtures/index.html').read_text(encoding='utf-8')


class ModuleTests(unittest.TestCase):
    def test_home_gets_the_block_in_head_once(self):
        page = ua_home_blocks.apply(home())
        head = page[:page.index('</head>')]
        self.assertEqual(page.count('<!--UA-HOME-BLOCKS-V1-->'), 1)
        self.assertIn('<style id="ua-home-blocks">', head)
        self.assertEqual(ua_home_blocks.apply(page), page)
        self.assertEqual(ua_home_blocks.remove(page), home())

    def test_only_css_is_added(self):
        page = ua_home_blocks.apply(home())
        added = page.replace(home()[:home().index('</head>')], '', 1)
        self.assertEqual(len(page) - len(home()), len('<!--UA-HOME-BLOCKS-V1--><!--/UA-HOME-BLOCKS-V1-->')
                         + len(ua_home_blocks.STYLE))
        self.assertTrue(added.startswith('<!--UA-HOME-BLOCKS-V1-->' + ua_home_blocks.STYLE))

    def test_other_pages_unchanged(self):
        for name in ('katalog.html', 'card.html', 'podbor.html'):
            text = (HERE/'fixtures'/name).read_text(encoding='utf-8')
            self.assertEqual(ua_home_blocks.apply(text), text)

    def test_style_matches_the_approved_mockup(self):
        mockup = (HERE/'mockup.css').read_text(encoding='utf-8')
        for rule in ('rgba(232,200,125,.34)', 'border-radius:22px', 'top:-19px', 'rotate(45deg)',
                     '.hero.ua-order-first{overflow:visible', 'margin:44px 40px 0'):
            self.assertIn(rule, mockup)
            self.assertIn(rule, ua_home_blocks.STYLE)

    def test_head_helper_is_the_installed_one(self):
        digest = hashlib.sha256((HERE/'ua_head_block.py').read_bytes()).hexdigest()
        self.assertEqual(digest, candidate_builder.DEPENDENCY_SHA256['ua_head_block.py'])


class BuildTests(unittest.TestCase):
    def source(self):
        installed = INJECT.rstrip('\n') + ('\n\n# PERF-CWV-001\n_ua_perf_base_inject = inject_html\n'
                                           'def inject_html(source):\n    return _ua_perf_base_inject(source)\n')
        return {'site_ge_inject.py': installed.encode('utf-8'), 'video/index.html': home().encode('utf-8')}

    def dependencies(self):
        return {'ua_head_block.py': (HERE/'ua_head_block.py').read_bytes()}

    def test_candidate(self):
        result = candidate_builder.build(self.source(), self.dependencies())
        self.assertEqual(set(result), {'ua_home_blocks.py', 'site_ge_inject.py', 'video/index.html'})
        inject = result['site_ge_inject.py'].decode('utf-8')
        self.assertTrue(inject.endswith(candidate_builder.INJECT_TAIL))
        compile(inject, 'site_ge_inject.py', 'exec')
        self.assertIn('<!--UA-HOME-BLOCKS-V1-->', result['video/index.html'].decode('utf-8'))

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, 'HOME_BLOCKS_DEPENDENCY'):
            candidate_builder.build(self.source(), {'ua_head_block.py': b'other'})
        result = candidate_builder.build(self.source(), self.dependencies())
        with self.assertRaisesRegex(ValueError, 'HOME_BLOCKS_ALREADY_APPLIED'):
            candidate_builder.edit('site_ge_inject.py', result['site_ge_inject.py'])
        with self.assertRaisesRegex(ValueError, 'HOME_BLOCKS_INJECT_MISSING'):
            candidate_builder.edit('site_ge_inject.py', INJECT.encode('utf-8'))


if __name__ == '__main__':
    unittest.main()
