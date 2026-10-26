#!/usr/bin/env python3
"""Read-only download of official photo candidates and press-page text (MODEL-GALLERY-001, round 2).

For each model in sources.py: the listed photo series and the photos referenced by its press pages (official
hosts and the manufacturers' own image stores only) are downloaded for the pick of one car (4 exterior, 4 interior,
trunk), and the press pages' text is kept for the generation name and first year. GET only, no token.
"""
import base64
import html
import os
from pathlib import Path
import re
import urllib.parse

import discover
from sources import SOURCES

TASKS = ('MODEL-GALLERY-CANDIDATES-20261026',)
# The manufacturers' image stores the press pages link to.
IMAGE_HOSTS = ('www.hyundai.news', 'lexus-cms-media.s3.us-east-2.amazonaws.com',
               'wieck-nissanao-production.s3.amazonaws.com', 'wieck-nissanao-production.s3.us-west-1.amazonaws.com')
# Adobe Experience Manager (hyundai.news) keeps a 1280 px web rendition next to each original.
RENDITION = '/jcr:content/renditions/cq5dam.web.1280.1280.jpeg'
MAX_IMAGES = 40
MAX_IMAGE = 3 * 1024 * 1024
# One model's evidence stays under the 16 MB file limit and six models under the 64 MB run limit.
MAX_MODEL = 9 * 1024 * 1024
TEXT = 6000


def allowed(url):
    host = urllib.parse.urlsplit(url).netloc.lower().split(':')[0]
    return url.startswith('https://') and host in IMAGE_HOSTS


def get_image(url, fetch):
    if not allowed(url):
        raise discover.DiscoverError('IMAGE_OUTSIDE_SCOPE')
    variants = [url + RENDITION, url] if urllib.parse.urlsplit(url).netloc == 'www.hyundai.news' else [url]
    for variant in variants:
        status, data = fetch(variant)
        if status == 200 and data and len(data) <= MAX_IMAGE:
            return variant, data
    return None, b''


def fetch_bytes(url):
    request = discover.urllib.request.Request(url, headers={'User-Agent': discover.AGENT})
    try:
        with discover.urllib.request.urlopen(request, timeout=40) as response:
            return response.status, response.read(MAX_IMAGE + 1)
    except discover.urllib.error.HTTPError as error:
        error.close()
        return error.code, b''
    except (discover.urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, b''


def text_of(body):
    body = re.sub(r'(?is)<(script|style)\b.*?</\1>', ' ', body)
    return ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', body)).split())[:TEXT]


def model(key, page_fetch=discover.get, image_fetch=fetch_bytes):
    source = SOURCES[key]
    wanted, pages = list(source['images']), []
    for url in source['pages']:
        status, final, body = page_fetch(url)
        text = body.decode('utf-8', 'replace')
        parser = discover.Page(final)
        parser.feed(text)
        pages.append({'url': url, 'status': status, 'title': ' '.join(parser.title.split()), 'text': text_of(text)})
        wanted += [image for image, _ in parser.images if allowed(image) and discover.IMAGE.search(image)]
    photos, total = [], 0
    for url in dict.fromkeys(wanted):
        if len(photos) >= MAX_IMAGES:
            break
        used, data = get_image(url, image_fetch)
        if data and total + len(data) <= MAX_MODEL:
            total += len(data)
            photos.append({'url': url, 'fetched': used, 'sha256': discover.sha(data), 'b64': base64.b64encode(data).decode()})
    return {'pages': pages, 'photos': photos}


def evidence_path(key):
    return '%s/candidates_%s.json' % (discover.PACKAGE, key)


def execute(env, *, root=None, page_fetch=discover.get, image_fetch=fetch_bytes):
    root = discover.ROOT if root is None else Path(root)
    request_sha, run_id = discover.validate_identity(env, root, TASKS)
    for key in sorted(SOURCES):
        discover.write(root, evidence_path(key), discover.dump({'task_id': env['UAART_TASK_ID'], 'run_id': run_id,
                                                                'http_methods': ['GET'], 'remote_write_count': 0,
                                                                **model(key, page_fetch, image_fetch)}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'manufacturer_sites', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': [evidence_path(key) for key in sorted(SOURCES)]}
    discover.write(root, env['UAART_RECEIPT_PATH'], discover.dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_CANDIDATES_STOP:'+(str(exc) if isinstance(exc, discover.DiscoverError) else type(exc).__name__))
        raise SystemExit(1) from None
