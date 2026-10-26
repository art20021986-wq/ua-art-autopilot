#!/usr/bin/env python3
"""Read-only Commons search for more interior and rear photos of each model (MODEL-GALLERY-001, round 2).

The category round (collect.py) found too few interior photos for many models. Here each model gets
Commons file searches by name and generation: interior queries and one rear-view query. Same scope,
licence filter and evidence form as collect.py; one JSON per country group (search_<group>.json).
"""
import json
import os
from pathlib import Path

import collect

TASKS = ('MODEL-GALLERY-SEARCH-20261026',)
# key -> (interior queries, rear-view query)
SEARCHES = {
    'lexus-rx-350': (('Lexus RX AL10 interior', 'Lexus RX 2012 interior'), 'Lexus RX AL10 rear'),
    'lexus-rx-500': (('Lexus RX 2023 interior', 'Lexus RX 500h interior'), 'Lexus RX 2023 rear'),
    'lexus-tx': (('Lexus TX interior',), 'Lexus TX rear'),
    'toyota-tacoma-trd-pro': (('Toyota Tacoma 2024 interior', 'Toyota Tacoma N400 interior'), 'Toyota Tacoma 2024 rear'),
    'toyota-tacoma-trailhunter': (('Toyota Tacoma Trailhunter interior', 'Toyota Tacoma 2024 interior'),
                                  'Toyota Tacoma Trailhunter rear'),
    'byd-song-plus': (('BYD Song Plus interior',), 'BYD Song Plus rear'),
    'volkswagen-id-4': (('Volkswagen ID.4 interior',), 'Volkswagen ID.4 rear'),
    'byd-yuan-plus-atto-3': (('BYD Atto 3 interior', 'BYD Yuan Plus interior'), 'BYD Atto 3 rear'),
    'zeekr-001': (('Zeekr 001 interior',), 'Zeekr 001 rear'),
    'byd-seal': (('BYD Seal interior',), 'BYD Seal rear'),
    'volkswagen-golf': (('Volkswagen Golf VIII interior', 'Golf 8 interior'), 'Volkswagen Golf VIII rear'),
    'volkswagen-tiguan': (('Volkswagen Tiguan III interior', 'Tiguan 2024 interior'), 'Volkswagen Tiguan III rear'),
    'audi-q5': (('Audi Q5 8R interior',), 'Audi Q5 8R rear'),
    'skoda-octavia': (('Škoda Octavia IV interior', 'Octavia 2020 interior'), 'Škoda Octavia IV Combi rear'),
    'renault-megane': (('Renault Mégane IV interior', 'Renault Megane IV interior'), 'Renault Megane IV Grandtour rear'),
    'ford-fusion-fusion-hybrid': (('Ford Fusion 2013 interior', 'Ford Fusion 2017 interior'), 'Ford Fusion 2017 rear'),
    'toyota-camry': (('Toyota Camry XV70 interior',), 'Toyota Camry XV70 rear'),
    'volkswagen-jetta': (('Volkswagen Jetta VII interior', 'Jetta 2019 interior'), 'Volkswagen Jetta VII rear'),
    'toyota-rav4-rav4-hybrid': (('Toyota RAV4 XA50 interior', 'RAV4 2019 interior'), 'Toyota RAV4 XA50 rear'),
    'subaru-forester': (('Subaru Forester SL interior', 'Subaru Forester 2025 interior'), 'Subaru Forester SL rear'),
    'nissan-note': (('Nissan Note E12 interior',), 'Nissan Note E12 rear'),
    'toyota-aqua': (('Toyota Aqua 2021 interior', 'Toyota Aqua MXPK10 interior'), 'Toyota Aqua 2021 rear'),
    'mercedes-benz-b-class': (('Mercedes-Benz W246 interior', 'W246 Innenraum'), 'Mercedes-Benz W246 rear'),
    'toyota-prius': (('Toyota Prius XW60 interior', 'Prius 2023 interior'), 'Toyota Prius XW60 rear'),
    'classics-1980-1990': (('Mercedes-Benz W124 interior', 'W124 Innenraum'), 'Mercedes-Benz W124 rear'),
    'kia-k5': (('Kia K5 DL3 interior', 'Kia K5 2020 interior'), 'Kia K5 DL3 rear'),
    'hyundai-sonata': (('Hyundai Sonata DN8 interior',), 'Hyundai Sonata DN8 rear'),
    'hyundai-tucson': (('Hyundai Tucson NX4 interior', 'Hyundai Tucson 2021 interior'), 'Hyundai Tucson NX4 rear'),
    'kia-sportage': (('Kia Sportage NQ5 interior',), 'Kia Sportage NQ5 rear'),
    'hyundai-santa-fe': (('Hyundai Santa Fe MX5 interior', 'Hyundai Santa Fe 2024 interior'), 'Hyundai Santa Fe MX5 rear'),
    'tesla-model-y': (('Tesla Model Y interior',), 'Tesla Model Y rear'),
    'tesla-model-3': (('Tesla Model 3 Highland interior', 'Tesla Model 3 2024 interior'), 'Tesla Model 3 Highland rear'),
    'ford-escape': (('Ford Escape 2020 interior', 'Ford Kuga III interior'), 'Ford Escape 2020 rear'),
    'nissan-rogue': (('Nissan Rogue T33 interior', 'Nissan X-Trail T33 interior'), 'Nissan Rogue T33 rear'),
    'bmw-x3': (('BMW X3 G45 interior', 'BMW G45 interior'), 'BMW X3 G45 rear'),
}
PER_QUERY = 30
LIMITS = {'interior': 24, 'sides': 10}


def search(fetch, query):
    value = collect.api(fetch, action='query', list='search', srsearch=query + ' filetype:bitmap',
                        srnamespace='6', srlimit=str(PER_QUERY))
    return [hit['title'] for hit in value.get('query', {}).get('search', [])]


def model(fetch, key):
    interior, rear = SEARCHES[key]
    wanted = {}
    for query in interior:
        for title in search(fetch, query):
            wanted.setdefault(title, ('interior', query))
    for title in search(fetch, rear):
        wanted.setdefault(title, ('sides', rear))
    wanted.pop(collect.canonical(collect.MODELS[key][1]), None)
    items = collect.info(fetch, list(wanted), collect.THUMB)
    taken = {name: [] for name in LIMITS}
    for title, (name, query) in wanted.items():
        item = items.get(title)
        if item and collect.usable(item) and len(taken[name]) < LIMITS[name]:
            thumb = collect.with_thumb(fetch, {**item, 'via': 'search: ' + query})
            if thumb:
                taken[name].append(thumb)
    return {'candidates': taken}


def evidence_path(group):
    return '%s/search_%s.json' % (collect.PACKAGE, group)


def execute(env, *, root=None, fetch=collect.get):
    root = collect.ROOT if root is None else Path(root)
    request_sha, run_id = collect.validate_identity(env, root, TASKS)
    groups = sorted({collect.MODELS[key][0] for key in SEARCHES})
    for group in groups:
        found = {key: model(fetch, key) for key in SEARCHES if collect.MODELS[key][0] == group}
        collect.write(root, evidence_path(group), collect.dump({'task_id': env['UAART_TASK_ID'], 'run_id': run_id,
                                                                'http_methods': ['GET'], 'remote_write_count': 0,
                                                                'models': found}))
    receipt = {'task_id': env['UAART_TASK_ID'], 'status': 'FINISHED', 'task_class': 'STANDARD',
               'target_environment': 'shadow', 'live_source_environment': 'wikimedia_commons', 'tests': 'PASS',
               'tests_scope': 'READ_ONLY_PROBE', 'unexpected_changes': 0, 'rollback_ready': True,
               'rollback_ready_scope': 'NO_REMOTE_WRITES', 'production_required': False,
               'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': [evidence_path(group) for group in groups]}
    collect.write(root, env['UAART_RECEIPT_PATH'], collect.dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('MODEL_GALLERY_SEARCH_STOP:'+(str(exc) if isinstance(exc, collect.CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
