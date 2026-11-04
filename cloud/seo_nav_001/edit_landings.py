"""ua_seo_landings (FINANCE-001, owner 2026-11-04): the landing pages' navigation line keeps only «Умови».

Owner: remove «Головна», «Каталог», «Підбір авто» and the other-language link from the line under the top block,
keep «Умови». The site top block (ua_seo_header) carries the logo link home and RU / UA to the page versions; the
hreflang alternates in <head> are unchanged. One edit in _page; its now unused «other» language goes with it.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_landings.py'
OLD = ("    other = LANGS[1 - LANGS.index(lang)]\n"
       "    meta = '<meta name=\"%s\" content=\"%s\">' % (MODEL_META, escape('|'.join(key))) if isinstance(key, tuple) else ''\n"
       "    nav = ('<a href=\"/video/index.html\">{home}</a><a href=\"/video/katalog.html\">{catalog}</a>'\n"
       "           '<a href=\"/video/podbor.html\">{order}</a><a href=\"/video/info.html\">{terms}</a>'\n"
       "           '<a href=\"/video/%s\" hreflang=\"%s\" lang=\"%s\">{other}</a>' % (path(other, key), other, other)).format(**t)\n")
NEW = ("    meta = '<meta name=\"%s\" content=\"%s\">' % (MODEL_META, escape('|'.join(key))) if isinstance(key, tuple) else ''\n"
       "    nav = '<a href=\"/video/info.html\">{terms}</a>'.format(**t)  # owner 2026-11-04: only «Умови»\n")


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or NEW in text:
        raise ValueError('LANDINGS_NAV_FRAGMENT')
    return text.replace(OLD, NEW).encode('utf-8')
