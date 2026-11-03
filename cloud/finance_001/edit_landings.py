"""ua_seo_landings (FINANCE-001): the finance page among the landing pages.

Three small edits: import ua_seo_finance, path() knows the finance page's slug, pages() writes it through
the generator's own _page (canonical, hreflang uk/ru, navigation, footer), so the sitemap, IndexNow and the
Google sitemap ping pick it up like every other landing page. Each original fragment must occur exactly once
and an applied fragment is refused.
"""
NAME = 'ua_seo_landings.py'

HELPER = '''def finance_page(lang, existing):
    """FINANCE-001: credit and leasing partners (ua_seo_finance, data in ua_finance_partners)."""
    page = finance.page(lang, T[lang]['home'], ORIGIN + '/video/index.html', url(path(lang, FINANCE)))
    return _page(lang, FINANCE, page['title'], page['desc'], page['h1'], page['body'], page['head'], existing)


'''

EDITS = (
    ('import ua_seo_schema as schema\n',
     'import ua_seo_schema as schema\nimport ua_finance_partners\nimport ua_seo_finance as finance  # FINANCE-001\n'),
    ("PRICE = 'price'  # the \"how much does it cost\" page, in place of a model key\n",
     "PRICE = 'price'  # the \"how much does it cost\" page, in place of a model key\n"
     "FINANCE = 'finance'  # the credit and leasing page (FINANCE-001), in place of a model key\n"),
    ("    elif key in order_models.TOPICS:  # SEO-CONTENT-001\n",
     "    elif key == FINANCE:\n        name = ua_finance_partners.SLUG[lang]\n"
     "    elif key in order_models.TOPICS:  # SEO-CONTENT-001\n"),
    ("def pages(cars, kept_keys=(), existing=frozenset()):\n", HELPER + "def pages(cars, kept_keys=(), existing=frozenset()):\n"),
    ("        for name in order_models.TOPICS:\n            result[path(lang, name)] = topic(lang, name, existing)\n",
     "        for name in order_models.TOPICS:\n            result[path(lang, name)] = topic(lang, name, existing)\n"
     "        result[path(lang, FINANCE)] = finance_page(lang, existing)\n"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('LANDINGS_FRAGMENT_NOT_UNIQUE:' + old[:40])
        text = text.replace(old, new)
    return text.encode('utf-8')
