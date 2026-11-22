"""katalog.html and info.html declared Ukrainian in their source (SEO-FIX-20261121, answer 3).

The site shows both pages in Ukrainian by default (the language script, data-uk texts) and keeps the Russian text for
its switcher, but the source said lang="ru" with Russian title and description. Only the head changes now: lang="uk",
the title text and the description / og content take the page's own data-uk texts. The body stays (the switcher
reads it). ua_seo_metadata.normalize keeps the same at every later publication (edit_metadata)."""
import re

import tags

NAMES = ('video/katalog.html', 'video/info.html')
DESCRIPTIONS = (r'<meta\s+name="description"[^>]*>', r'<meta\s+property="og:title"[^>]*>',
                r'<meta\s+property="og:description"[^>]*>')


def build(value):
    source = value.decode('utf-8')
    html = tags.find(source, r'<html\b[^>]*>')
    if tags.attributes(html).get('lang') != 'ru':
        raise ValueError('SOURCE_NOT_RUSSIAN')
    result = tags.replace_once(source, html, re.sub(r'\blang\s*=\s*(["\']).*?\1', 'lang="uk"', html, count=1))
    title = re.findall(r'(<title\b[^>]*>)(.*?)(</title>)', result, flags=re.S | re.I)
    if len(title) != 1:
        raise ValueError('TITLE_COUNT')
    opening, text, closing = title[0]
    result = tags.replace_once(result, opening + text + closing, opening + tags.attributes(opening)['data-uk'] + closing)
    for pattern in DESCRIPTIONS:
        found = re.findall(pattern, result, flags=re.I | re.S)
        if not found:
            continue
        old = tags.find(result, pattern)
        result = tags.replace_once(result, old, tags.with_attribute(old, 'content', tags.attributes(old)['data-uk-content']))
    return result.encode('utf-8')
