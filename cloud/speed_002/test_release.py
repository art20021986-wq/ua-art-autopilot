#!/usr/bin/env python3
"""SPEED-002: card URL versions, stage picture copies, order page styles and the exact edits."""
from io import BytesIO
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    from PIL import Image
except ImportError:  # the runner has no Pillow; the server has it (CARD-LANG-PROBE-20261101: Pillow 10.4.0, WebP)
    Image = None

import candidate_builder as builder
import ua_card_urls as urls
import ua_stage_images as stage

STAGE = ('<a class="stage-card stage-split-v203" href="katalog.html?f=kiev"><picture class="stage-picture">'
         '<source srcset="/video/preview/v4/assets/ai/03_stage_kiev_v3.webp" type="image/webp">'
         '<img class="stage-ai" src="/video/opt/x.webp" alt=""></picture>'
         '<img class="stage-live" style="a" data-mcf-foto="1" src="/video/stage/UA-0002.webp?v=034537" alt="Фото"></a>')
HOME = '<html><body><h1>Home</h1>' + STAGE + '<p>end</p></body></html>'
LINKS = ''.join('<link rel="stylesheet" href="order/%s.css?v=20261030.1">' % name
                for name in ('order',) + builder.LATER_STYLES + ('search-picker',))
ORDER = '<html><head>' + LINKS + '</head><body></body></html>'
CATALOG = '<article><a class="catalog-photo" href="UA-0001.html"><img src="x"></a><a href="UA-0001.html">→</a></article>' \
          '<article><a href="UA-0002.html"></a></article>'


def webp(width, height=100):
    out = BytesIO()
    Image.new('RGB', (width, height)).save(out, 'WEBP')
    return out.getvalue()


class CardUrlTests(unittest.TestCase):
    def test_versions_only_when_they_exist(self):
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder)
            for name in ('ua/UA-0001.html', 'ru/UA-0001.html'):
                (video/name).parent.mkdir(parents=True, exist_ok=True)
                (video/name).write_text('x')
            with patch.object(urls, 'VIDEO', video):
                self.assertEqual(urls.preferred('https://www.uaart.com.ua/video/UA-0001.html', 'ru'),
                                 'https://www.uaart.com.ua/video/ru/UA-0001.html')
                self.assertEqual(urls.preferred('/video/UA-0001.html', 'uk'), '/video/ua/UA-0001.html')
                self.assertEqual(urls.preferred('/video/UA-0002.html', 'uk'), '/video/UA-0002.html')
                self.assertEqual(urls.preferred('/video/UA-0001.html', 'ka'), '/video/UA-0001.html')
                self.assertEqual(urls.for_lang([{'url': '/video/UA-0001.html', 'name': 'A'}], 'uk'),
                                 [{'url': '/video/ua/UA-0001.html', 'name': 'A'}])
                linked = urls.catalog_links(CATALOG)
        self.assertEqual(linked.count('href="ua/UA-0001.html"'), 2)
        self.assertIn('href="UA-0002.html"', linked)
        self.assertEqual(urls.catalog_links(linked), linked)


class StageImageTests(unittest.TestCase):
    def test_srcset_added_once_markup_kept(self):
        find = lambda url: (stage.copy_url(url), 880)
        done = stage.apply(HOME, find=find)
        self.assertEqual(done.count('srcset="/video/opt/s/'), 2)
        self.assertIn('<source srcset="/video/opt/s/preview_v4_assets_ai_03_stage_kiev_v3.webp 600w, '
                      '/video/preview/v4/assets/ai/03_stage_kiev_v3.webp 880w" sizes="%s" type="image/webp">'
                      % stage.SIZES, done)
        self.assertIn('src="/video/stage/UA-0002.webp?v=034537" srcset="/video/opt/s/stage_UA-0002.webp 600w, '
                      '/video/stage/UA-0002.webp?v=034537 880w"', done)
        self.assertEqual(stage.apply(done, find=find), done)
        # The home stage button sets a new live photo (?v=) and drops its srcset: it is added back.
        repicked = re.sub(r'(class="stage-live"[^>]*?)src="[^"]*" srcset="[^"]*" sizes="[^"]*"',
                          r'\1src="/video/stage/UA-0009.webp?v=1a2b3c4d"', done)
        self.assertNotIn('stage_UA-0009', repicked)
        again = stage.apply(repicked, find=find)
        self.assertIn('src="/video/stage/UA-0009.webp?v=1a2b3c4d" srcset="/video/opt/s/stage_UA-0009.webp 600w, '
                      '/video/stage/UA-0009.webp?v=1a2b3c4d 880w"', again)
        self.assertEqual(again.count('srcset="/video/opt/s/'), 2)
        self.assertEqual(stage.apply(HOME, find=lambda url: None), HOME)
        self.assertEqual(stage.apply('<p>other page</p>'), '<p>other page</p>')

    @unittest.skipIf(Image is None, 'Pillow is on the server, not on the runner')
    def test_copy_made_and_small_originals_left(self):
        data, width = stage.small(webp(1320))
        with Image.open(BytesIO(data)) as image:
            self.assertEqual((image.width, width), (600, 1320))
        self.assertIsNone(stage.small(webp(500)))
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder)
            (video/'stage').mkdir()
            (video/'stage/UA-0002.webp').write_bytes(webp(880))
            with patch.object(stage, 'VIDEO', video):
                self.assertEqual(stage.ensure('/video/stage/UA-0002.webp'), ('/video/opt/s/stage_UA-0002.webp', 880))
                self.assertTrue((video/'opt/s/stage_UA-0002.webp').is_file())
                self.assertIsNone(stage.ensure('/video/stage/UA-0009.webp'))


class BuildTests(unittest.TestCase):
    def sources(self):
        return {name: ('# head\n' + ''.join(old + '\n# between\n' for old, _ in edits)).encode()
                for name, edits in builder.EDITS.items()}

    def test_exact_edits_pages_and_copies(self):
        source = self.sources()
        source.update({'video/katalog.html': CATALOG.encode(), 'video/index.html': HOME.encode(),
                       'video/podbor.html': ORDER.encode()})
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder)
            (video/'ua').mkdir()
            (video/'ua/UA-0001.html').write_text('x')
            with patch.object(urls, 'VIDEO', video), patch.object(stage, 'small', lambda data: (b'copy', 1320)):
                result = builder.build(source, {}, lambda url: b'original')
        for name, edits in builder.EDITS.items():
            for _, new in edits:
                self.assertIn(new, result[name].decode())
        self.assertIn('href="ua/UA-0001.html"', result['video/katalog.html'].decode())
        self.assertEqual(result['video/index.html'].decode().count('srcset="/video/opt/s/'), 2)
        self.assertEqual(sorted(n for n in result if n.startswith('video/opt/s/')),
                         ['video/opt/s/preview_v4_assets_ai_03_stage_kiev_v3.webp', 'video/opt/s/stage_UA-0002.webp'])
        order = result['video/podbor.html'].decode()
        self.assertEqual(order.count('media="print" onload="this.media=\'all\'"'), 5)
        self.assertEqual(order.count('<noscript>'), 5)
        self.assertIn('<link rel="stylesheet" href="order/order.css?v=20261030.1">', order)
        self.assertIn('<link rel="stylesheet" href="order/search-picker.css?v=20261030.1">', order)

    def test_refusals(self):
        for change in ('missing', 'duplicate', 'applied'):
            source = self.sources()
            old = builder.EDITS['ua_seo_catalog.py'][0][0]
            text = source['ua_seo_catalog.py'].decode()
            text = {'missing': text.replace(old, ''), 'duplicate': text + old, 'applied': text + '# SPEED-002\n'}[change]
            source['ua_seo_catalog.py'] = text.encode()
            with self.assertRaises(ValueError, msg=change):
                builder.build(source, {}, lambda url: None)
        with self.assertRaisesRegex(ValueError, 'SPEED2_STYLES'):
            builder.build({'video/podbor.html': ORDER.replace('gallery', 'other').encode()}, {}, lambda url: None)
        with self.assertRaisesRegex(ValueError, 'SPEED2_UNCHANGED'):
            builder.build({'video/index.html': HOME.encode()}, {}, lambda url: None)


if __name__ == '__main__':
    unittest.main()
