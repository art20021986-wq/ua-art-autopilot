"""Company JSON-LD in the home page head; the rest of the page is kept byte for byte.

The home counters are patched in place by ua_site_counters, so the block persists.
"""
import re

import ua_seo_schema as schema

OWN = re.compile(r'<script type="application/ld\+json" id="%s">.*?</script>' % schema.SCRIPT_ID, re.S)


def build(source):
    text = source.decode('utf-8')
    lang = 'uk' if re.search(r'<html\b[^>]*\blang=["\']uk', text, re.I) else 'ru'
    block = schema.script(schema.dealer(lang))
    if OWN.search(text):
        return OWN.sub(lambda m: block, text, count=1).encode('utf-8')
    if len(re.findall(r'</head\s*>', text, re.I)) != 1 or 'application/ld+json' in text:
        raise ValueError('HOME_HEAD')
    return re.sub(r'</head\s*>', lambda m: block + m.group(), text, count=1, flags=re.I).encode('utf-8')
