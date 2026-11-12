"""ua_seo_order_models (SEO-UKRAINE-PAGE-001): register the all-Ukraine topic page.

Its texts live in ua_seo_ukraine_page.TOPIC; this edit only adds it to TOPICS, right after the dict, so
ua_seo_landings renders, links and lists it like the other topic pages. The fragment must occur exactly once and an
applied edit is refused.
"""
NAME = 'ua_seo_order_models.py'
OLD = '\n# SEO-CONTENT-001: the custom-order page'
NEW = ('\nfrom ua_seo_ukraine_page import TOPIC as _UKRAINE  # SEO-UKRAINE-PAGE-001\n'
       "TOPICS['ukraine'] = _UKRAINE\n" + OLD)


def build(source):
    text = source.decode('utf-8')
    if text.count(OLD) != 1 or 'SEO-UKRAINE-PAGE-001' in text:
        raise ValueError('MODELS_FRAGMENT')
    return text.replace(OLD, NEW).encode('utf-8')
