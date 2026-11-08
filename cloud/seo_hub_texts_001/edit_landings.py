"""ua_seo_landings (SEO-HUB-TEXTS-001): the owner-approved sections on the Korea hub and the custom-order page.

Texts live in ua_seo_hub_texts. Here only placement: the hub gets «why UA ART», «most ordered models» and
«how we check» right after its intro; the custom-order page gets «how ordering works» after «what you get» and
three more questions (also in its FAQPage markup). Each original fragment must occur exactly once and an
applied fragment is refused.
"""
NAME = 'ua_seo_landings.py'

EDITS = (
    ("import ua_seo_schema as schema\n",
     "import ua_seo_schema as schema\nimport ua_seo_hub_texts as hub_texts  # SEO-HUB-TEXTS-001\n"),
    ("    body = ('<p>%s</p><h2>%s</h2>%s<h2>%s</h2>%s<p><a href=\"/video/katalog.html\">%s</a></p>%s%s' % (\n"
     "        escape(t['hub_intro'].format(**fill)), t['models'], _model_links(groups, lang),\n",
     "    body = ('<p>%s</p>%s<h2>%s</h2>%s<h2>%s</h2>%s<p><a href=\"/video/katalog.html\">%s</a></p>%s%s' % (\n"
     "        escape(t['hub_intro'].format(**fill)), hub_texts.hub(lang, lambda key: '/video/' + path(lang, key)),\n"
     "        t['models'], _model_links(groups, lang),\n"),
    ("    pairs = [(q, a) for q, a in t['order_faq']] + list(extra['faq'])\n",
     "    pairs = [(q, a) for q, a in t['order_faq']] + list(extra['faq']) + list(hub_texts.ORDER_FAQ[lang])\n"),
    ("    body = ('<p>%s</p>%s<h2>%s</h2><ul class=\"models\">%s</ul>",
     "    body = ('<p>%s</p>%s%s<h2>%s</h2><ul class=\"models\">%s</ul>"),
    ("        escape(t['order_intro']), _gets(extra), t['order_countries'], countries,",
     "        escape(t['order_intro']), _gets(extra), hub_texts.order_steps(lang), t['order_countries'], countries,"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('LANDINGS_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
