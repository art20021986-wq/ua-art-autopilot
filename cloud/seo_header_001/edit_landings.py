"""ua_seo_landings (FINANCE-001 stage 5): every landing page starts with the site's top block (ua_seo_header).

One import and two edits in _page, the one function that writes every landing page's frame: the top block goes
right after <body>, before the page's own navigation line, and its styles join the page's style. RU / UA in the
block link the page's own language versions. Each original fragment must occur exactly once and an applied
fragment is refused.
"""
NAME = 'ua_seo_landings.py'
EDITS = (
    ('import ua_seo_schema as schema\n',
     'import ua_seo_schema as schema\nimport ua_seo_header as site_header  # FINANCE-001 stage 5\n'),
    ("</head><body><header><nav>%s</nav></header>", "</head><body>%s<header><nav>%s</nav></header>"),
    ("url(path(lang, key)), CSS, ld, nav, escape(h1), body, footer)",
     "url(path(lang, key)), CSS + site_header.CSS, ld,\n"
     "        site_header.header(lang, {l: '/video/' + path(l, key) for l in LANGS}), nav, escape(h1), body, footer)"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('LANDINGS_FRAGMENT_NOT_UNIQUE:' + old[:40])
        text = text.replace(old, new)
    return text.encode('utf-8')
