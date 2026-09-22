"""Exact offline reconciliation of two captured stale UA-0018 catalog slots.

No original file is overwritten, no DB row is changed, and the strict initial
price migration remains unchanged. This is bound to one actual observation.
"""
import hashlib
import json
import re

from initial_html_prices import Structure, _classes, _one

OBSERVER_SHA256 = '07e07f499c20d5db62e0ae58cb4922be2cfacd4e8956879dbcd374322bb71454'
ORIGINAL_CATALOG_SHA256 = '279a221536aecd36111d496482f1bbf8594f38ed7cc19fb77561faed27fc6d01'
TARGETS = frozenset(('site/katalog.html', 'video/katalog.html'))
EXPECTED_ROW = {'auto_number': 'UA-0018', 'id': 28, 'price_georgia': None,
                'price_uah': 22900, 'published': 1, 'status': 'ua_arrived'}
OLD_FRAGMENT = '<b data-ru="19 900 $" data-uk="19 900 $">19 900 $</b>'
NEW_FRAGMENT = '<b data-ru="22 900 $" data-uk="22 900 $">22 900 $</b>'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()


def reconcile_catalogs(html, rows, observer_raw):
    if sha(observer_raw) != OBSERVER_SHA256:
        raise ValueError('RECONCILIATION_EXACT_ACTUAL_OBSERVER_REQUIRED')
    observed = json.loads(observer_raw)
    # Canonical preflight supplies full CRM rows. Bind their actual public
    # fields to the observed rows without altering or discarding full rows
    # passed by the caller to the strict price migrator and alias checks.
    fields = ('id', 'auto_number', 'published', 'status', 'price_uah', 'price_georgia')
    public_rows = [{key: row.get(key) for key in fields} for row in rows]
    if (observed.get('status') != 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION'
            or observed.get('export_completed') is not True or observed.get('blockers')
            or public_rows != observed['published_rows']
            or sha(encoded(public_rows)) != observed['database']['published_sha256']
            or observed['database'] != observed['second_database']):
        raise ValueError('RECONCILIATION_ACTUAL_STABLE_ROWS_REQUIRED')
    matches = [row for row in public_rows if row.get('auto_number') == 'UA-0018']
    if matches != [EXPECTED_ROW] or not TARGETS <= set(html):
        raise ValueError('RECONCILIATION_EXACT_CAR_IDENTITY_AND_TARGETS_REQUIRED')
    prepared, pages = dict(html), {}
    for name in sorted(TARGETS):
        original = html[name]
        if (sha(original) != ORIGINAL_CATALOG_SHA256
                or observed['core_html'][name]['sha256'] != sha(original)
                or observed['core_html'][name]['bytes'] != len(original)):
            raise ValueError('RECONCILIATION_EXACT_ORIGINAL_CATALOG_REQUIRED:' + name)
        source = original.decode('utf-8')
        structure = Structure(source)
        articles = [node for node in structure.elements if node.tag == 'article'
                    and 'catalog-card' in _classes(node)
                    and 'UA-0018' in source[node.start:node.end]]
        article = _one(articles, 'RECONCILIATION_UNIQUE_CAR_ARTICLE_REQUIRED')
        if set(re.findall(r'UA-[0-9]{4,}', source[article.start:article.end])) != {'UA-0018'}:
            raise ValueError('RECONCILIATION_ARTICLE_IDENTITY_MISMATCH')
        top = _one([node for node in structure.elements if node.tag == 'div'
                    and 'catalog-top' in _classes(node)
                    and article.start < node.start < article.end],
                   'RECONCILIATION_UNIQUE_PRICE_TOP_REQUIRED')
        price = _one([node for node in top.children if node.tag == 'b'],
                     'RECONCILIATION_UNIQUE_PRICE_NODE_REQUIRED')
        if (price.start, price.end) != (19028, 19081) or source[price.start:price.end] != OLD_FRAGMENT:
            raise ValueError('RECONCILIATION_EXACT_OBSERVED_PRICE_SLOT_REQUIRED')
        result = source[:price.start] + NEW_FRAGMENT + source[price.end:]
        if result[:price.start] != source[:price.start] or result[price.start + len(NEW_FRAGMENT):] != source[price.end:]:
            raise AssertionError('RECONCILIATION_OUTSIDE_PRICE_CHANGED')
        prepared[name] = result.encode('utf-8')
        pages[name] = {'original_sha256': sha(original), 'intermediate_sha256': sha(prepared[name]),
            'car_id': 28, 'auto_number': 'UA-0018', 'observed_catalog_ua_usd': 19900,
            'actual_committed_crm_ua_usd': 22900, 'char_start': price.start, 'char_end': price.end,
            'old_fragment': OLD_FRAGMENT, 'new_fragment': NEW_FRAGMENT,
            'outside_exact_price_slot_unchanged': True, 'captured_original_overwritten': False}
    if any(prepared[name] != raw for name, raw in html.items() if name not in TARGETS):
        raise AssertionError('RECONCILIATION_OTHER_HTML_CHANGED')
    return prepared, {'contract': 'PR114-BOUND-CATALOG-UA-RECONCILIATION-1',
        'status': 'EXACT_OFFLINE_INTERMEDIATE_DERIVED_NOT_INSTALLED',
        'observer_sha256': OBSERVER_SHA256, 'database': observed['database'],
        'schema_sha256': observed['schema_sha256'], 'current_row': EXPECTED_ROW,
        'pages': pages, 'strict_initial_price_guard_changed': False,
        'database_changed': False, 'installation_authority': False}
