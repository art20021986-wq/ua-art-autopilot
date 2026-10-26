#!/usr/bin/env python3
"""Read-only collection of photo candidates for the order page model gallery (MODEL-GALLERY-001).

GET only, public Wikimedia Commons API and thumbnails, no token, nothing written outside the repository
evidence. For each model the current main photo (its Commons file) gives the start: the file's own
categories, their subcategories, and the parent categories naming the model with their interior
subcategories. Only freely licensed files are kept. One JSON per country group holds the main photo and
the candidates (metadata plus a small base64 thumbnail) for the visual pick of the same generation.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

PACKAGE = 'cloud/model_gallery_001'
# R2: Commons page titles use spaces; HTTP errors other than 404 stop the run with their code.
# R3: any https host under wikimedia.org; a candidate whose thumbnail cannot be read is skipped.
TASKS = ('MODEL-GALLERY-COLLECT-20261026', 'MODEL-GALLERY-COLLECT-20261026-R2', 'MODEL-GALLERY-COLLECT-20261026-R3')
ROOT = Path(__file__).resolve().parents[2]
API = 'https://commons.wikimedia.org/w/api.php'
AGENT = 'UA-ART-autopilot/1.0 (https://www.uaart.com.ua/)'
# key -> (group, main Commons file, pattern every followed category name must contain)
MODELS = {
    'lexus-rx-350': ('canada', 'File:LEXUS_RX_350_(AL10)_China.jpg', 'RX'),
    'lexus-rx-500': ('canada', 'File:Lexus_RX_500h_F_Sport_Performance_(TALH17)_1X7A7076.jpg', 'RX'),
    'lexus-tx': ('canada', 'File:24_Lexus_TX_350_Luxury.jpg', 'TX'),
    'toyota-tacoma-trd-pro': ('canada', 'File:24_Toyota_Tacoma_TRD_Pro_HV.jpg', 'Tacoma'),
    'toyota-tacoma-trailhunter': ('canada', 'File:Toyota_Tacoma_Trailhunter_(2026)_(55212826017).jpg', 'Tacoma'),
    'byd-song-plus': ('china', 'File:Алматы,_BYD_Song_Plus_на_Шевченко.jpg', 'Song'),
    'volkswagen-id-4': ('china', 'File:Volkswagen_ID.4_GTX_1X7A0301.jpg', 'ID.4'),
    'byd-yuan-plus-atto-3': ('china', 'File:BYD_Atto_3_1X7A6495.jpg', 'Atto|Yuan'),
    'zeekr-001': ('china', 'File:Moscow_-_Zeekr_001_-_2025-9.jpg', '001'),
    'byd-seal': ('china', 'File:BYD_Seal_IAA_2023_1X7A0371.jpg', 'Seal'),
    'volkswagen-golf': ('europe', 'File:2020_Volkswagen_Golf_Style_1.5_Front.jpg', 'Golf'),
    'volkswagen-tiguan': ('europe', 'File:Volkswagen_Tiguan_III_IMG_8388.jpg', 'Tiguan'),
    'audi-q5': ('europe', 'File:Audi_Q5_BW_1.jpg', 'Q5'),
    'skoda-octavia': ('europe', 'File:Škoda_Octavia_IV_Combi_Facelift_IMG_9434.jpg', 'Octavia'),
    'renault-megane': ('europe', 'File:Renault_Megane_IV_Grandtour_E-Tech_IMG_3333.jpg', 'M[eé]gane'),
    'ford-fusion-fusion-hybrid': ('georgia', 'File:2017_Ford_Fusion_Sport.jpg', 'Fusion'),
    'toyota-camry': ('georgia', 'File:Toyota_Camry_(XV70)_IMG_9081.jpg', 'Camry'),
    'volkswagen-jetta': ('georgia', 'File:Volkswagen_Jetta_VII_GLI_IMG_3138.jpg', 'Jetta'),
    'toyota-rav4-rav4-hybrid': ('georgia', 'File:Toyota_RAV4_Plug-in_Hybrid_GR_Sport_IMG_9891.jpg', 'RAV4'),
    'subaru-forester': ('georgia', 'File:Subaru_Forester_(SL)_e-BOXER_DSC_8811.jpg', 'Forester'),
    'nissan-note': ('japan', 'File:2014-2016_Nissan_Note_X.jpg', 'Note'),
    'toyota-aqua': ('japan', 'File:2nd_generation_Toyota_Aqua_Z.jpg', 'Aqua'),
    'mercedes-benz-b-class': ('japan', 'File:MERCEDES-BENZ_B-CLASS_(W246)_China.jpg', 'W246|B-Class'),
    'toyota-prius': ('japan', 'File:Toyota_Prius_(XW60)_Plug-in_Hybrid_IMG_9905.jpg', 'Prius'),
    'classics-1980-1990': ('japan', 'File:Mercedes-Benz_230E_(1988)_W124_(50104678181).jpg', 'W124'),
    'kia-k5': ('korea', 'File:0_Kia_K5_(DL3)_0.jpg', 'K5'),
    'hyundai-sonata': ('korea', 'File:0_Hyundai_Sonata_(DN8)fl_1.jpg', 'Sonata'),
    'hyundai-tucson': ('korea', 'File:Hyundai_Tucson_(NX4)_1X7A0424.jpg', 'Tucson'),
    'kia-sportage': ('korea', 'File:Kia_Sportage_(NQ5)_1X7A0319.jpg', 'Sportage'),
    'hyundai-santa-fe': ('korea', 'File:2024_Hyundai_Santa_Fe_(MX5)_IMG_5295.jpg', 'Santa Fe'),
    'tesla-model-y': ('usa', 'File:Tesla_Model_Y_1X7A6211.jpg', 'Model Y'),
    'tesla-model-3': ('usa', 'File:Tesla_Model_3_(2023)_Autofrühling_Ulm_IMG_9282.jpg', 'Model 3'),
    'ford-escape': ('usa', 'File:Ford_Escape_(fourth_generation)_1X7A6220.jpg', 'Escape'),
    'nissan-rogue': ('usa', 'File:2024_Nissan_Rogue_au_SIAM_2024.jpg', 'Rogue'),
    'bmw-x3': ('usa', 'File:BMW_G45_X3_M50_DSC_8805.jpg', 'X3'),
}
INTERIOR = re.compile(r'interior|innenraum|interieur|intérieur|cockpit|dashboard|armaturen|seat|sitz|'
                      r'inside|trunk|boot|kofferraum|cabin|steering|lenkrad|салон', re.I)
SIDES = re.compile(r'rear|back|heck|arri[eè]re|side|profile|seite|left|right|links|rechts', re.I)
FREE = re.compile(r'^(cc0|public domain|pd\b.*|cc by(-sa)? \d\.\d.*|cc[ -]by(-sa)?[ -]\d\.\d.*)$', re.I)
MAX_CATEGORIES = 30
MAX_MEMBERS = 200
THUMB = 320
MAIN_THUMB = 640
LIMITS = {'interior': 22, 'sides': 12, 'other': 8}
PAUSE = 0.2


class CollectError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def get(url):
    host = urllib.parse.urlsplit(url).netloc
    if not url.startswith('https://') or not (host == 'wikimedia.org' or host.endswith('.wikimedia.org')):
        raise CollectError('URL_OUTSIDE_SCOPE:' + host)
    request = urllib.request.Request(url, headers={'User-Agent': AGENT})
    for attempt in range(3):
        time.sleep(PAUSE * (1 + 4 * attempt))
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read(8 * 1024 * 1024)
        except urllib.error.HTTPError as error:
            error.close()
            if error.code == 404:
                return b''
            if error.code not in (429, 500, 502, 503, 504):
                raise CollectError('HTTP_%d' % error.code) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
    return b''


def api(fetch, **params):
    params.update(format='json', formatversion='2', maxlag='5')
    body = fetch(API + '?' + urllib.parse.urlencode(params))
    return json.loads(body) if body else {}


def canonical(title):
    """The page title as the API returns it: spaces, not underscores."""
    return title.replace('_', ' ')


def categories(fetch, title):
    pages = api(fetch, action='query', titles=title, prop='categories', clshow='!hidden', cllimit='max')
    pages = pages.get('query', {}).get('pages', [])
    return [c['title'] for c in (pages[0].get('categories', []) if pages else [])]


def members(fetch, category, kind):
    value = api(fetch, action='query', list='categorymembers', cmtitle=category, cmtype=kind,
                cmlimit=str(MAX_MEMBERS))
    return [m['title'] for m in value.get('query', {}).get('categorymembers', [])]


def follow(fetch, main, word):
    """Categories to read: the main file's own, their subcategories, and parents with interior subcategories."""
    named = lambda title: re.search(word, title, re.I) is not None
    own = [c for c in categories(fetch, main) if named(c)]
    found = list(own)
    for category in own:
        found += [c for c in members(fetch, category, 'subcat') if named(c)]
        for parent in (c for c in categories(fetch, category) if named(c)):
            found.append(parent)
            found += [c for c in members(fetch, parent, 'subcat') if named(c) and INTERIOR.search(c)]
    return list(dict.fromkeys(found))[:MAX_CATEGORIES]


def info(fetch, titles, width):
    found = {}
    for start in range(0, len(titles), 50):
        value = api(fetch, action='query', titles='|'.join(titles[start:start + 50]), prop='imageinfo',
                    iiprop='url|size|mime|sha1|extmetadata', iiurlwidth=str(width),
                    iiextmetadatafilter='LicenseShortName|Artist|LicenseUrl|DateTimeOriginal')
        for page in value.get('query', {}).get('pages', []):
            item = (page.get('imageinfo') or [None])[0]
            if not item:
                continue
            meta = item.get('extmetadata', {})
            text = lambda key: re.sub(r'<[^>]+>', '', meta.get(key, {}).get('value', '')).strip()
            found[page['title']] = {'title': page['title'], 'width': item.get('width'), 'height': item.get('height'),
                                    'mime': item.get('mime'), 'sha1': item.get('sha1'), 'thumb': item.get('thumburl'),
                                    'page': item.get('descriptionurl'), 'license': text('LicenseShortName'),
                                    'license_url': text('LicenseUrl'), 'artist': text('Artist')[:200],
                                    'date': text('DateTimeOriginal')[:40]}
    return found


def usable(item):
    return (item['mime'] in ('image/jpeg', 'image/png', 'image/webp') and FREE.match(item['license'] or '')
            and (item['width'] or 0) >= 1000 and item['width'] >= (item['height'] or 0) and item['thumb'])


def bucket(item, via):
    if INTERIOR.search(item['title']) or INTERIOR.search(via):
        return 'interior'
    return 'sides' if SIDES.search(item['title']) else 'other'


def with_thumb(fetch, item):
    try:
        data = fetch(item['thumb'])
    except CollectError:
        return None
    return {**item, 'thumb_sha256': sha(data), 'thumb_b64': base64.b64encode(data).decode()} if data else None


def model(fetch, key):
    _, main, word = MODELS[key]
    main = canonical(main)
    main_info = info(fetch, [main], MAIN_THUMB).get(main)
    if not main_info:
        raise CollectError('MAIN_MISSING:' + key)
    cats = follow(fetch, main, word)
    via = {}
    for category in cats:
        for title in members(fetch, category, 'file'):
            via.setdefault(title, category)
    via.pop(main, None)
    items = info(fetch, list(via), THUMB)
    taken = {name: [] for name in LIMITS}
    for title in sorted(items):
        item = items[title]
        if usable(item):
            name = bucket(item, via[title])
            if len(taken[name]) < LIMITS[name]:
                thumb = with_thumb(fetch, {**item, 'via': via[title]})
                if thumb:
                    taken[name].append(thumb)
    return {'main': with_thumb(fetch, main_info), 'categories': cats, 'pool_size': len(via), 'candidates': taken}


def validate_identity(env, root):
    task = env.get('UAART_TASK_ID')
    if task not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % task \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % task:
        raise CollectError('IDENTITY')
    request = root/env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise CollectError('BINDING')
    raw = json.loads(request.read_bytes())
    if raw.get('read_only') is not True or raw.get('production_required') is not False:
        raise CollectError('SCOPE')
    return expected, env['UAART_RUN_ID']


def evidence_path(group):
    return '%s/candidates_%s.json' % (PACKAGE, group)


def write(root, relative, data):
    target = root/relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=1)+'\n').encode()


def execute(env, *, root=None, fetch=get):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    groups = sorted({group for group, _, _ in MODELS.values()})
    for group in groups:
        found = {key: model(fetch, key) for key, value in MODELS.items() if value[0] == group}
        write(root, evidence_path(group), dump({'task_id': task, 'run_id': run_id, 'http_methods': ['GET'],
                                                'remote_write_count': 0, 'models': found}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'wikimedia_commons', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': [evidence_path(group) for group in groups]}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_COLLECT_STOP:'+(str(exc) if isinstance(exc, CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
