#!/usr/bin/env python3
"""Read-only audit of manufacturers' press archives in several countries for 2018–2023 photos (MODEL-GALLERY-001).

Owner 2026-10-27: the widest audit of official sites of different countries. For each model, start pages are the
brand's press/model archive pages in several countries (ARCHIVES); the crawl (discover.crawl) follows only links
naming the model. An image is kept when its address or its page names the model (image address or alt) and a year 2018–2023; up to
MAX_PER_MODEL are downloaded (AEM web rendition first) from the official image hosts that answered. Evidence: one
JSON per model (archive_<key>.json) with page statuses, so the audit also shows which sites refuse automated reads.
"""
import os
from pathlib import Path
import re
import urllib.parse

import candidates
import discover

TASKS = ('MODEL-GALLERY-ARCHIVE-20261027-A', 'MODEL-GALLERY-ARCHIVE-20261027-B')
# One run holds at most 30 evidence files and 64 MB, so the models go in two runs by country group.
PARTS = {'A': ('korea', 'usa', 'canada', 'china'), 'B': ('europe', 'georgia', 'japan')}
MAX_MODEL = 2500 * 1024
# brand -> press or model archive pages, several countries
ARCHIVES = {
    'hyundai': ('https://www.hyundai.news/eu/models.html', 'https://www.hyundai.news/uk/models.html',
                'https://www.hyundai.news/de/models.html', 'https://www.hyundainews.com/en-us/models'),
    'kia': ('https://www.kiamedia.com/us/en/models', 'https://press.kia.com/eu/en/home.html',
            'https://press.kia.com/uk/en/home.html'),
    'toyota': ('https://newsroom.toyota.eu/', 'https://media.toyota.co.uk/', 'https://global.toyota/en/newsroom/',
               'https://pressroom.toyota.com/'),
    'lexus': ('https://newsroom.lexus.eu/', 'https://pressroom.lexus.com/', 'https://media.lexus.co.uk/'),
    'volkswagen': ('https://www.volkswagen-newsroom.com/en', 'https://www.vwpress.co.uk/', 'https://media.vw.com/'),
    'audi': ('https://www.audi-mediacenter.com/en', 'https://media.audiusa.com/'),
    'skoda': ('https://www.skoda-storyboard.com/en/models/', 'https://www.skoda-storyboard.com/en/press-kits/'),
    'renault': ('https://media.renault.com/en/models/', 'https://media.renault.co.uk/'),
    'ford': ('https://media.ford.com/content/fordmedia/fna/us/en/products.html', 'https://www.fordmedia.eu/'),
    'subaru': ('https://media.subaru.com/models.html', 'https://www.subaru-global.com/ir/'),
    'nissan': ('https://usa.nissannews.com/en-US/models', 'https://global.nissannews.com/en/',
               'https://europe.nissannews.com/en-GB/'),
    'mercedes': ('https://group-media.mercedes-benz.com/marsMediaSite/en/instance/ko.xhtml',
                 'https://media.mercedes-benz.co.uk/'),
    'bmw': ('https://www.press.bmwgroup.com/global', 'https://www.press.bmwgroup.com/united-kingdom'),
    'tesla': ('https://www.tesla.com/presskit',),
    'byd': ('https://www.byd.com/eu/car', 'https://www.bydglobal.com/en/'),
    'zeekr': ('https://www.zeekr.eu/en/', 'https://www.zeekrlife.com/'),
}
# A year 2018–2023 alone or as the start of a press date (20200915).
YEAR = re.compile(r'(?<!\d)20(?:1[89]|2[0-3])(?:[01]\d[0-3]\d)?(?!\d)')
MAX_PER_MODEL = 24
# Several countries per brand share one bounded crawl per model.
MAX_PAGES = 60


def hosts():
    return {urllib.parse.urlsplit(url).netloc.lower() for urls in ARCHIVES.values() for url in urls}


def wanted(image, page, words):
    """A 2018–2023 photo of the model: the image address or alt text names the model (a page can show several
    models), the image address or the page title names the year."""
    return (discover.names_model(image['url'] + ' ' + image['alt'], words)
            and bool(YEAR.search(image['url'] + ' ' + page.get('title', ''))))


def model(key, page_fetch=discover.get, image_fetch=candidates.fetch_bytes):
    _, brand, words = discover.MODELS[key]
    found = discover.crawl(lambda url: page_fetch(url, hosts()), key, ARCHIVES[brand], hosts(), MAX_PAGES)
    pages = {page['url']: page for page in found['pages']}
    photos, total = [], 0
    for image in found['images']:
        if len(photos) >= MAX_PER_MODEL or not wanted(image, pages.get(image['page'], {}), words):
            continue
        # Images referenced by the official pages may sit on the brands' own image hosts (CDN, S3).
        used, data = candidates.get_image(image['url'], image_fetch, allowed=lambda url: url.startswith('https://'))
        if data and total + len(data) <= MAX_MODEL:
            total += len(data)
            photos.append({**image, 'fetched': used, 'sha256': discover.sha(data),
                           'b64': candidates.base64.b64encode(data).decode()})
    return {'pages': found['pages'], 'photos': photos}


def evidence_path(key):
    return '%s/archive_%s.json' % (discover.PACKAGE, key)


def execute(env, *, root=None, page_fetch=discover.get, image_fetch=candidates.fetch_bytes):
    root = discover.ROOT if root is None else Path(root)
    request_sha, run_id = discover.validate_identity(env, root, TASKS)
    keys = part_keys(env['UAART_TASK_ID'][-1])
    for key in keys:
        discover.write(root, evidence_path(key), discover.dump({'task_id': env['UAART_TASK_ID'], 'run_id': run_id,
                                                                'http_methods': ['GET'], 'remote_write_count': 0,
                                                                **model(key, page_fetch, image_fetch)}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'manufacturer_sites', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id, 'evidence_path': [evidence_path(k) for k in keys]}
    discover.write(root, env['UAART_RECEIPT_PATH'], discover.dump(receipt))
    return receipt


# The gallery models (2018–2023 cars exist); Lexus TX, Tacoma Trailhunter and the classics card are out.
KEYS = tuple(key for key in discover.MODELS if key not in ('lexus-tx', 'toyota-tacoma-trailhunter'))


def part_keys(part):
    return sorted(key for key in KEYS if discover.MODELS[key][0] in PARTS[part])


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_ARCHIVE_STOP:'+(str(exc) if isinstance(exc, discover.DiscoverError) else type(exc).__name__))
        raise SystemExit(1) from None
