import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from candidate_builder import ROOT_APPLICATION, routing
from ua_seo_metadata import Document, normalize, page_name, text
from ua_seo_sitemap import sitemap, sync_after_write


class SEOTests(unittest.TestCase):
    def test_card_is_escaped_and_preserves_business_body(self):
        source = '''<html lang="ru"><head><title>Old</title><link rel="canonical" href="https://www.uaart.com.ua/video/UA-0003.html"></head><body><h1>Kia K5 2019</h1><table><tr><td>Пробег</td><td>181 000 км</td></tr><tr><td>Двигатель</td><td>1 999 см³, газ</td></tr></table><img src="foto/UA-0003/1.jpg" alt=""><script>let price = 500; let s = '<img>';</script><a href="UA-0003-diag.html">Диагностика</a></body></html>'''
        result = normalize(source, 'UA-0003.html')
        self.assertEqual(result, normalize(result, 'UA-0003.html'))
        doc = Document(result)
        self.assertIn('181 000 км', text(doc.select('title')[0]))
        self.assertEqual(doc.select('img')[0]['attrs']['src'], 'foto/UA-0003/1.jpg')
        self.assertEqual(doc.select('img')[0]['attrs']['alt'], 'Kia K5 2019 — фото 1')
        self.assertIn("let price = 500; let s = '<img>';", result)
        self.assertIn('<td>181 000 км</td>', result)
        self.assertEqual(normalize('<html>diagnostics</html>', 'UA-0003-diag.html'), '<html>diagnostics</html>')

    def test_canonical_precedes_brand_title_classifier(self):
        source = '<title>UA ART COMPANY</title><link rel="canonical" href="https://www.uaart.com.ua/video/podbor.html">'
        self.assertEqual(page_name(source), 'podbor.html')
        self.assertEqual(page_name(source.replace('podbor.html', 'UA-0003.html')), '')

    def test_sitemap_excludes_orphan_external_missing_and_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)/'video'
            root.mkdir()
            for name in ('index.html','katalog.html','UA-0003.html','UA-9999.html','UA-0003-diag.html'):
                (root/name).write_text('page')
            catalog = ('<a href="UA-0003.html?v=2">car</a><a href="UA-0003.html">duplicate</a>'
                       '<a href="UA-0004.html">missing</a><a href="UA-0003-diag.html">diag</a>'
                       '<a href="https://example.org/UA-9999.html">external</a>')
            (root/'katalog.html').write_text(catalog)
            values = [node.text for node in ET.fromstring(sitemap(root)).iter() if node.tag.endswith('loc')]
            self.assertEqual(len(values), 3)
            self.assertIn('https://www.uaart.com.ua/video/UA-0003.html', values)
            self.assertFalse(any('9999' in item or 'diag' in item or '?' in item for item in values))
            sync_after_write(root/'katalog.html', catalog)
            self.assertEqual((root/'sitemap.xml').read_bytes(), sitemap(root))

    def test_root_redirect_and_unknown_404_get_head(self):
        namespace = {'CEL': 'https://www.uaart.com.ua/video/index.html'}
        exec(compile(ROOT_APPLICATION, 'root_application', 'exec'), namespace)
        app = namespace['application']
        for method in ('GET', 'HEAD'):
            output = []
            response = app({'PATH_INFO':'/', 'REQUEST_METHOD':method,'QUERY_STRING':'lang=uk'}, lambda status, headers: output.append((status,dict(headers))))
            self.assertEqual(output[0][0], '301 Moved Permanently')
            self.assertTrue(output[0][1]['Location'].endswith('?lang=uk'))
            self.assertEqual(response, [])
            output.clear()
            response = app({'PATH_INFO':'/video/missing.html', 'REQUEST_METHOD':method}, lambda status, headers: output.append((status,dict(headers))))
            self.assertEqual(output[0][0], '404 Not Found')
            self.assertNotIn('Location', output[0][1])
            self.assertEqual(bool(response), method == 'GET')

    def test_route_patch_preserves_existing_wrappers(self):
        source = '''def application(environ, start_response):
    return []
application = api_wrapper(application)
def _ua_seo068_wsgi_payload(path):
    if path == '/robots.txt':
        return b'robots', 'text/plain'
    if path == '/sitemap.xml':
        return b'old', 'application/xml'
    return None
application = order_wrapper(application)
'''
        result = routing(source)
        self.assertIn('application = api_wrapper(application)', result)
        self.assertIn('application = order_wrapper(application)', result)
        self.assertIn("return b'robots', 'text/plain'", result)
        self.assertIn("sitemap('/home/Carix/video')", result)


if __name__ == '__main__':
    unittest.main()
