"""Contract checks over complete rendered HTML before any production write."""
import re
from ua_seo_metadata import CARD, Document, normalize, text


def fingerprint(doc):
    """Business attributes and embedded programs must remain exactly intact."""
    return {
        'scripts': [(n['attrs'], doc.source[n['open_end']:n['inner_end']]) for n in doc.select('script')],
        'inputs': [n['attrs'] for tag in ('input','select','option','textarea','button','form','video','source') for n in doc.select(tag)],
        'images': [{k:v for k,v in n['attrs'].items() if k not in ('alt','data-ru-alt','data-uk-alt')} for n in doc.select('img')],
        'cells': [text(n) for n in doc.select('td')],
        'business_data': [{k:v for k,v in n['attrs'].items() if k.startswith('data-ua-')}
                          for n in doc.nodes if any(k.startswith('data-ua-') for k in n['attrs'])],
    }


def verify_page(before, after, name):
    original, current = Document(before), Document(after)
    assert fingerprint(original) == fingerprint(current), 'BUSINESS_CONTENT:' + name
    assert normalize(after, name) == after, 'IDEMPOTENCE:' + name
    assert len(current.select('title')) == 1, 'TITLE_COUNT:' + name
    descriptions = [n for n in current.select('meta') if n['attrs'].get('name') == 'description']
    assert len(descriptions) == 1 and descriptions[0]['attrs'].get('content'), 'DESCRIPTION:' + name
    canonicals = [n['attrs'].get('href') for n in current.select('link') if n['attrs'].get('rel') == 'canonical']
    assert canonicals == ['https://www.uaart.com.ua/video/' + name], 'CANONICAL:' + name
    assert len(current.select('h1')) == 1, 'HEADING:' + name
    assert not any('noindex' in n['attrs'].get('content','').lower() for n in current.select('meta')
                   if n['attrs'].get('name') in ('robots','googlebot')), 'NOINDEX:' + name
    old_links = [n['attrs'].get('href') for n in original.select('a')]
    added_intro = next((n for n in current.select('p') if n['attrs'].get('id') == 'ua-seo-order-intro'), None)
    had_intro = any(n['attrs'].get('id') == 'ua-seo-order-intro' for n in original.select('p'))
    new_links = [n['attrs'].get('href') for n in current.select('a')
                 if not (added_intro and not had_intro and added_intro['start'] < n['start'] < added_intro['end'])]
    assert old_links == new_links, 'LINKS:' + name
    if CARD.fullmatch(name):
        assert all(n['attrs'].get('alt') or n['attrs'].get('role') == 'presentation'
                   or n['attrs'].get('aria-hidden') == 'true'
                   for n in current.select('img') if '/foto/' in '/' + n['attrs'].get('src','')), 'IMAGE_ALT:' + name
    return {'file': name, 'title': text(current.select('title')[0]),
            'description': descriptions[0]['attrs']['content'],
            'images': len(current.select('img')), 'canonical': canonicals[0]}
