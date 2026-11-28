"""ua_seo_metadata.py tail (SEO-PRICE-001): card_facts takes the price from ua_seo_price when the page has no block yet."""
NAME = 'ua_seo_metadata.py'
MARK = 'SEO-PRICE-001'
TAIL = ('\n\n# SEO-PRICE-001: the price for the title, description and JSON-LD even before the price block is put in.\n'
        '_ua_seo_price_base_card_facts = card_facts\n'
        'def card_facts(doc, source, name):\n'
        '    facts = _ua_seo_price_base_card_facts(doc, source, name)\n'
        '    if facts.get(\'price_usd\') is None:\n'
        '        import ua_seo_price\n'
        '        facts[\'price_usd\'] = ua_seo_price.price_usd(source)\n'
        '    return facts\n')


def build(value):
    text = value.decode('utf-8')
    if MARK in text:
        raise ValueError('SEO_PRICE_ALREADY_APPLIED')
    if 'def card_facts(doc, source, name):' not in text or "'price_usd':" not in text:
        raise ValueError('SEO_PRICE_CARD_FACTS_MISSING')
    return (text.rstrip('\n') + TAIL).encode('utf-8')
