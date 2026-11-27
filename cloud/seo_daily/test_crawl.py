import unittest

import crawl

HTML = ('<html lang="uk"><head><title>Каталог авто</title><meta name="description" content="%s">'
        '<meta name="viewport" content="width=device-width"><link rel="canonical" href="https://www.uaart.com.ua/video/a.html">'
        '<link rel="alternate" hreflang="ru" href="/video/ru/a.html"><script type="application/ld+json">'
        '{"@context":"https://schema.org","@graph":[{"@type":"Organization"},{"@type":"FAQPage"}]}</script></head>'
        '<body><h1>Авто <b>з Кореї</b></h1><a href="/video/b.html#x">b</a><a href="/api/x">api</a></body></html>' % ('о' * 100))


def page(html=HTML, **extra):
    value = crawl.parse(html)
    value.update(url='https://www.uaart.com.ua/video/a.html', final='https://www.uaart.com.ua/video/a.html',
                 status=200, seconds=0.2)
    value.update(extra)
    return value


class CrawlTest(unittest.TestCase):
    def test_parse_fields(self):
        value = crawl.parse(HTML)
        self.assertEqual(value['lang'], 'uk')
        self.assertEqual(value['h1'], ['Авто з Кореї'])
        self.assertEqual(value['ld'], ['Organization', 'FAQPage'])
        self.assertEqual(value['hreflang'], [['ru', '/video/ru/a.html']])

    def test_clean_page_has_no_issues(self):
        self.assertEqual(crawl.issues(page()), [])

    def test_issues_found(self):
        html = HTML.replace('<h1>', '<h1>x</h1><h1>').replace('rel="canonical" href="https://www.uaart.com.ua/video/a.html"',
                                                           'rel="canonical" href="https://www.uaart.com.ua/video/z.html"')
        html = html.replace('</head>', '<meta name="robots" content="noindex"><script type="application/ld+json">{</script></head>')
        found = crawl.issues(page(html, seconds=5))
        self.assertIn('h1 x2', found)
        self.assertIn('canonical -> https://www.uaart.com.ua/video/z.html', found)
        self.assertIn('noindex', found)
        self.assertIn('structured data invalid', found)
        self.assertIn('slow 5.0 s', found)

    def test_error_status_short(self):
        self.assertEqual(crawl.issues(page(status=404)), ['status 404'])

    def test_internal_links_skip_api_and_known(self):
        pages = [page()]
        self.assertEqual(crawl.internal_links(pages, []), ['https://www.uaart.com.ua/video/b.html'])
        self.assertEqual(crawl.internal_links(pages, ['https://www.uaart.com.ua/video/b.html']), [])


if __name__ == '__main__':
    unittest.main()
