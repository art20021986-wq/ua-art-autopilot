"""ua_seo_landings (SEO-CONTENT-001): topic pages, their links and the custom-order page additions.

Texts are data in ua_seo_order_models (TOPICS, ORDER_EXTRA). New here: path() knows a topic's slug, topic()
renders a topic page like the other landing pages, pages() writes them; the Japan page and the Korean model
pages a topic names link to it; the custom-order page gets its new title, «what you get» and two questions.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_landings.py'

HELPERS = '''def _topic_links(lang, where):
    """Links to the topic pages that belong to a page: 'japan', or a Korean model key."""
    return ''.join('<p><a href="/video/%s">%s</a></p>' % (path(lang, name), escape(topic[lang]['link']))
                   for name, topic in order_models.TOPICS.items() if where == topic['parent'] or where in topic['models'])


def _gets(extra):
    return '<h2>%s</h2><ul>%s</ul>' % (escape(extra['gets_title']), ''.join('<li>%s</li>' % escape(g) for g in extra['gets']))


def topic(lang, name, existing):
    """A stand-alone topic page (ua_seo_order_models.TOPICS): sections, its models, the order button, questions."""
    t, page = T[lang], order_models.TOPICS[name][lang]
    sections = ''.join('<h2>%s</h2><ul>%s</ul>' % (escape(head), ''.join('<li>%s</li>' % escape(x) for x in items))
                       for head, items in page['sections'])
    models = ''.join('<li><a href="/video/%s">%s</a></li>' % (path(lang, key), escape(model_name(key)))
                     for key in order_models.TOPICS[name]['models'])
    body = '<p>%s</p>%s%s<a class="cta" href="%s">%s</a><h2>%s</h2>%s<p><a href="/video/%s">%s</a></p>' % (
        escape(page['intro']), sections, ('<ul class="models">%s</ul>' % models) if models else '',
        escape(page['href']), escape(page['cta']), t['faq_title'],
        ''.join('<h3>%s</h3><p>%s</p>' % (escape(q), escape(a)) for q, a in page['faq']),
        path(lang, ORDER), escape(t['order_h1']))
    parent = ((order_models.JAPAN[lang]['h1'], url(path(lang, JAPAN))) if order_models.TOPICS[name]['parent'] == 'japan'
              else (t['hub_h1'], url(path(lang))))
    ld = schema.script(schema.dealer(lang),
                       schema.breadcrumbs([(t['home'], ORIGIN + '/video/index.html'), parent, (page['h1'], url(path(lang, name)))]),
                       schema.faq(list(page['faq'])))
    return _page(lang, name, page['title'], page['desc'], page['h1'], body, ld, existing)


'''

EDITS = (
    ("    elif key == PRICE:\n        name = PRICE_SLUG[lang]\n",
     "    elif key == PRICE:\n        name = PRICE_SLUG[lang]\n"
     "    elif key in order_models.TOPICS:  # SEO-CONTENT-001\n        name = order_models.TOPICS[key][lang]['slug']\n"),
    ("    pairs = [(q, a) for q, a in t['order_faq']]\n",
     "    extra = order_models.ORDER_EXTRA[lang]  # SEO-CONTENT-001\n"
     "    pairs = [(q, a) for q, a in t['order_faq']] + list(extra['faq'])\n"),
    ("    body = ('<p>%s</p><h2>%s</h2><ul class=\"models\">%s</ul>",
     "    body = ('<p>%s</p>%s<h2>%s</h2><ul class=\"models\">%s</ul>"),
    ("        escape(t['order_intro']), t['order_countries'], countries,",
     "        escape(t['order_intro']), _gets(extra), t['order_countries'], countries,"),
    ("    return _page(lang, ORDER, t['order_title'], t['order_desc'], t['order_h1'], body, ld, existing)\n",
     "    return _page(lang, ORDER, extra['title'], t['order_desc'], t['order_h1'], body, ld, existing)\n"),
    ("    models = ''.join('<h3>%s</h3><p>%s</p>' % (escape(name), escape(text)) for name, text in j['models'])\n",
     "    models = ''.join('<h3>%s</h3><p>%s</p>' % (escape(name), escape(text)) for name, text in j['models'])\n"
     "    models += _topic_links(lang, 'japan')\n"),
    ("    others = _model_links(groups, lang, key)\n",
     "    others = _model_links(groups, lang, key)\n    about += _topic_links(lang, key)\n"),
    ("def pages(cars, kept_keys=(), existing=frozenset()):\n", HELPERS + "def pages(cars, kept_keys=(), existing=frozenset()):\n"),
    ("        result[path(lang, PRICE)] = price(lang, cars, {k: v for k, v in listed.items() if v}, existing)\n",
     "        result[path(lang, PRICE)] = price(lang, cars, {k: v for k, v in listed.items() if v}, existing)\n"
     "        for name in order_models.TOPICS:\n            result[path(lang, name)] = topic(lang, name, existing)\n"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('LANDINGS_FRAGMENT_NOT_UNIQUE:' + old[:40])
        text = text.replace(old, new)
    return text.encode('utf-8')
