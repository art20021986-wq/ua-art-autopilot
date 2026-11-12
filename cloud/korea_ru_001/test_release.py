#!/usr/bin/env python3
"""KOREA-RU-001: the Russian Korea page, the Korea page head, the exact edits and the public sitemap poll."""
import importlib.machinery
import importlib.util
from pathlib import Path
import re
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def fixture_module(name, path):
    """ua_card_lang as live (CARD-CANONICAL-RU-001 fixture): ua_korea_ru takes its markup helpers from it."""
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loader.exec_module(module)
    return module


fixture_module('ua_card_lang', HERE/'fixtures'/'ua_card_lang.txt')
import candidate_builder as builder  # noqa: E402
import deployment_controller as controller  # noqa: E402
import ua_korea_ru as korea  # noqa: E402

LIVE = (HERE/'fixtures'/'korea_live.txt').read_text(encoding='utf-8')  # public /video/korea.html, 2026-11-12
SMALL = ('<!doctype html><html lang="uk"><head><script id="ua-art-site-languages" src="/video/ua-site-languages.js">'
         '</script><title data-uk="Аукціони" data-ru="Аукционы">Аукціони</title>'
         '<meta name="description" content="Обирайте" data-uk-content="Обирайте" data-ru-content="Выбирайте">'
         '<link rel="canonical" href="https://www.uaart.com.ua/video/korea.html">'
         '<link rel="stylesheet" href="ua-v203.css"></head><body>'
         '<a href="index.html" aria-label="Головна" data-ru-aria="Главная" data-uk-aria="Головна">'
         '<span data-ru="Каталог" data-uk="Каталог">Каталог</span></a>'
         '<p data-ru="Цена — на торгах" data-uk="Ціна — на торгах">Ціна — на торгах</p>'
         '<div data-ru="Блок">Текст <b>жирний</b></div>'
         '<script src="i18n-home-ge.js?v=1"></script>'
         '<script>a.href="podbor.html?strana="+c;img.src="\'+esc(p)+\'";</script></body></html>')


def visible(page):
    page = re.sub(r'(?is)<(script|style)\b.*?</\1>', '', page)
    return [x.strip() for x in re.split(r'<[^>]+>', page) if x.strip()]


class RussianPageTests(unittest.TestCase):
    def test_small_page(self):
        page = korea.page(SMALL)
        self.assertTrue(page.startswith('<!doctype html><html lang="ru"><head><link rel="canonical" '
                                        'href="https://www.uaart.com.ua/video/ru/korea.html">' + korea.links()))
        self.assertEqual(page.count('rel="canonical"'), 1)
        self.assertIn('>Аукционы</title>', page)
        self.assertIn('content="Выбирайте"', page)
        self.assertIn('aria-label="Главная"', page)
        self.assertIn('>Цена — на торгах</p>', page)
        self.assertIn('<div data-ru="Блок">Текст <b>жирний</b></div>', page)  # not the element's only child: kept
        self.assertIn('href="/video/index.html"', page)
        self.assertIn('href="/video/ua-v203.css"', page)
        self.assertIn('<script src="/video/i18n-home-ge.js?v=1"></script>', page)
        self.assertIn('a.href="/video/podbor.html?strana="+c;img.src="\'+esc(p)+\'";', page)  # script code kept
        self.assertIn('<meta name="%s" content="%s">' % (korea.MARK, korea.revision(SMALL)), page)

    def test_live_page_fully_russian(self):
        page = korea.page(LIVE)
        self.assertEqual([t for t in visible(page) if re.search('[іїєґІЇЄҐ]', t)], [])
        self.assertIn('<html lang="ru">', page)
        self.assertIn('Аукционы Кореи онлайн — UA ART COMPANY</title>', page)
        self.assertNotIn('src="/video/\'+', page)  # the lot photos stay as the script builds them
        # Every other byte of the lot block is the live one.
        block = lambda html: re.search(r'(?s)<script[^>]*>[^<]*?fetch\("/video/korea/lots\.json.*?</script>', html)[0]
        self.assertEqual(block(page), block(LIVE))

    def test_reconcile_writes_on_change_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'korea.html').write_text(SMALL, encoding='utf-8')
            self.assertEqual(korea.reconcile(root), {'written': ['ru/korea.html']})
            self.assertEqual(korea.reconcile(root), {'written': []})
            (root/'korea.html').write_text(SMALL.replace('Ціна', 'Ціни'), encoding='utf-8')
            self.assertEqual(korea.reconcile(root), {'written': ['ru/korea.html']})
            self.assertEqual((root/'ru/korea.html').read_text(encoding='utf-8'),
                             korea.page(SMALL.replace('Ціна', 'Ціни')))


class BuildTests(unittest.TestCase):
    def sources(self):
        value = {name: ('# head\n' + ''.join(old + '# between\n' for old, _ in edits)).encode()
                 for name, edits in builder.EDITS.items()}
        value[builder.KOREA] = LIVE.encode()
        return value

    def test_exact_edits_head_and_new_files(self):
        result = builder.build(self.sources(), {})
        for name, edits in builder.EDITS.items():
            for _, new in edits:
                self.assertIn(new, result[name].decode())
        page = result[builder.KOREA].decode()
        self.assertEqual(page, LIVE.replace('<head>', '<head>' + korea.links(), 1))
        self.assertEqual(result[builder.RUSSIAN].decode(), korea.page(page))
        self.assertEqual(result['ua_korea_ru.py'], (HERE/'ua_korea_ru.py').read_bytes())
        self.assertEqual(sorted(result), sorted(builder.targets(None) + ('ua_korea_ru.py', builder.RUSSIAN)))
        # The job rebuilds nothing right after the install: the page carries the installed korea.html's mark.
        self.assertIn(korea.revision(page), result[builder.RUSSIAN].decode())

    def test_refusals(self):
        for change in ('missing', 'duplicate', 'applied'):
            source = self.sources()
            old = builder.EDITS['ua_seo_sitemap.py'][0][0]
            text = source['ua_seo_sitemap.py'].decode()
            source['ua_seo_sitemap.py'] = {'missing': text.replace(old, ''), 'duplicate': text + old,
                                           'applied': text + '# KOREA-RU-001\n'}[change].encode()
            with self.assertRaises(ValueError, msg=change):
                builder.build(source, {})
        source = self.sources()
        source[builder.KOREA] = LIVE.replace('<head>', '<head>' + korea.links(), 1).encode()
        with self.assertRaisesRegex(ValueError, 'KOREA_RU_PAGE_HEAD'):
            builder.build(source, {})


class SitemapPollTests(unittest.TestCase):
    def test_waits_until_both_listed(self):
        both = ''.join('<loc>%s</loc>' % url for url in controller.KOREA_URLS)
        pages = iter(['<urlset/>', '<loc>%s</loc>' % controller.KOREA_URLS[0], both])
        sleeps = []
        self.assertEqual(controller.sitemap_lists_korea(lambda: next(pages), sleeps.append, lambda: 0),
                         list(controller.KOREA_URLS))
        self.assertEqual(len(sleeps), 2)

    def test_gives_up_after_deadline(self):
        clock = iter([0, controller.SITEMAP_WAIT_SECONDS + 1])
        with self.assertRaisesRegex(RuntimeError, 'SITEMAP_KOREA_MISSING:0'):
            controller.sitemap_lists_korea(lambda: '<urlset/>', lambda s: None, lambda: next(clock))

    def test_public_checks(self):
        page = korea.page(LIVE)
        self.assertTrue(controller.EXPECTED['/video/ru/korea.html'](page))
        self.assertFalse(controller.EXPECTED['/video/ru/korea.html'](LIVE))
        self.assertTrue(controller.EXPECTED['/video/korea.html'](LIVE.replace('<head>', '<head>' + korea.links(), 1)))
        self.assertFalse(controller.EXPECTED['/video/korea.html'](LIVE))


if __name__ == '__main__':
    unittest.main()
