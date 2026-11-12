"""ua_seo_landings (SEO-UKRAINE-PAGE-001): the custom-order page links the all-Ukraine page.

ua_seo_hub_texts.order_steps gets the page's address function, as hub() already does. The fragment must occur exactly
once and an applied edit is refused.
"""
NAME = 'ua_seo_landings.py'
OLD = 'hub_texts.order_steps(lang), '
NEW = "hub_texts.order_steps(lang, lambda key: '/video/' + path(lang, key)), "


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or NEW in text:
        raise ValueError('LANDINGS_FRAGMENT_NOT_UNIQUE')
    return text.replace(OLD, NEW).encode('utf-8')
