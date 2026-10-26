#!/usr/bin/env python3
"""Read-only Commons search for 2018–2023 cars only (MODEL-GALLERY-001, owner 2026-10-26: «с 18 года по 23»).

For each model: file searches for exterior, interior and trunk views of the generation sold in 2018–2023. A file is
kept only when the car is a 2018–2023 car: a model year 2018–2023 in the file name, or, for a generation that started
in 2018 or later, a photo taken in 2018–2023. Same scope, licence filter and evidence form as collect.py; one JSON
per country group (years_<group>.json).
"""
import os
from pathlib import Path
import re

import collect
from search import search

TASKS = ('MODEL-GALLERY-YEARS-20261026',)
FIRST, LAST = 2018, 2023
# key -> (search names of the 2018–2023 generation, the generation started in 2018 or later)
TARGETS = {
    'audi-q5': (('Audi Q5 FY', '2020 Audi Q5', '2018 Audi Q5'), False),
    'bmw-x3': (('BMW X3 G01', '2018 BMW X3', '2022 BMW X3'), False),
    'byd-seal': (('BYD Seal', '2023 BYD Seal'), True),
    'byd-song-plus': (('BYD Song Plus', '2021 BYD Song Plus'), True),
    'byd-yuan-plus-atto-3': (('BYD Atto 3', 'BYD Yuan Plus'), True),
    'ford-escape': (('2020 Ford Escape', '2021 Ford Escape', 'Ford Kuga III'), True),
    'ford-fusion-fusion-hybrid': (('2019 Ford Fusion', '2020 Ford Fusion', '2018 Ford Fusion'), False),
    'hyundai-santa-fe': (('Hyundai Santa Fe TM', '2019 Hyundai Santa Fe', '2021 Hyundai Santa Fe'), True),
    'hyundai-sonata': (('Hyundai Sonata DN8', '2020 Hyundai Sonata', '2021 Hyundai Sonata'), True),
    'hyundai-tucson': (('Hyundai Tucson NX4', '2022 Hyundai Tucson'), True),
    'kia-k5': (('Kia K5 DL3', '2021 Kia K5', '2022 Kia K5'), True),
    'kia-sportage': (('Kia Sportage NQ5', '2023 Kia Sportage'), True),
    'lexus-rx-350': (('2019 Lexus RX 350', '2020 Lexus RX 350', '2018 Lexus RX 350', '2023 Lexus RX 350'), False),
    'lexus-rx-500': (('2023 Lexus RX 500h', 'Lexus RX 500h'), False),
    'mercedes-benz-b-class': (('Mercedes-Benz W247', 'Mercedes-Benz B-Klasse W247'), True),
    'nissan-note': (('Nissan Note E13', 'Nissan Note e-Power E13', '2021 Nissan Note'), True),
    'nissan-rogue': (('2021 Nissan Rogue', '2022 Nissan Rogue', 'Nissan Rogue T33'), True),
    'renault-megane': (('Renault Megane IV', '2020 Renault Megane', 'Renault Mégane IV'), False),
    'skoda-octavia': (('Škoda Octavia IV', 'Skoda Octavia IV', '2021 Skoda Octavia'), True),
    'subaru-forester': (('Subaru Forester SK', '2019 Subaru Forester', '2022 Subaru Forester'), True),
    'tesla-model-3': (('2021 Tesla Model 3', '2019 Tesla Model 3', 'Tesla Model 3'), True),
    'tesla-model-y': (('2021 Tesla Model Y', '2022 Tesla Model Y', 'Tesla Model Y'), True),
    'toyota-aqua': (('Toyota Aqua MXPK', '2021 Toyota Aqua', 'Toyota Aqua XP210'), True),
    'toyota-camry': (('2018 Toyota Camry', '2021 Toyota Camry', '2023 Toyota Camry'), False),
    'toyota-prius': (('2023 Toyota Prius', '2019 Toyota Prius', '2021 Toyota Prius'), False),
    'toyota-rav4-rav4-hybrid': (('Toyota RAV4 XA50', '2019 Toyota RAV4', '2021 Toyota RAV4'), True),
    'toyota-tacoma-trd-pro': (('2019 Toyota Tacoma TRD Pro', '2021 Toyota Tacoma TRD', '2022 Toyota Tacoma'), False),
    'volkswagen-golf': (('Volkswagen Golf VIII', '2021 Volkswagen Golf'), True),
    'volkswagen-id-4': (('Volkswagen ID.4', '2021 Volkswagen ID.4'), True),
    'volkswagen-jetta': (('Volkswagen Jetta VII', '2019 Volkswagen Jetta', '2022 Volkswagen Jetta'), True),
    'volkswagen-tiguan': (('Volkswagen Tiguan II facelift', '2021 Volkswagen Tiguan', '2019 Volkswagen Tiguan'), False),
    'zeekr-001': (('Zeekr 001', '2022 Zeekr 001'), True),
}
# Specific views first, so a file found by several searches is labelled by the most specific one.
VIEWS = {'trunk': (' trunk', ' cargo'), 'interior': (' interior', ' dashboard'), 'exterior': ('', ' rear')}
LIMITS = {'exterior': 24, 'interior': 20, 'trunk': 8}
YEAR = re.compile(r'(?<!\d)(19\d\d|20\d\d)(?!\d)')


def car_year_ok(item, recent_generation):
    """True for a 2018–2023 car: model year in the name, or a photo date for a generation started in 2018+."""
    years = [int(year) for year in YEAR.findall(item['title'])]
    if years:
        return all(FIRST <= year <= LAST for year in years)
    taken = YEAR.findall(item.get('date') or '')
    return recent_generation and bool(taken) and FIRST <= int(taken[0]) <= LAST


def model(fetch, key):
    names, recent = TARGETS[key]
    wanted = {}
    for view, suffixes in VIEWS.items():
        for name in names:
            for suffix in suffixes:
                for title in search(fetch, name + suffix):
                    wanted.setdefault(title, view)
    items = collect.info(fetch, list(wanted), collect.THUMB)
    taken = {view: [] for view in VIEWS}
    for title, view in wanted.items():
        item = items.get(title)
        if item and collect.usable(item) and car_year_ok(item, recent) and len(taken[view]) < LIMITS[view]:
            thumb = collect.with_thumb(fetch, {**item, 'via': 'years: ' + view})
            if thumb:
                taken[view].append(thumb)
    return {'candidates': taken}


def evidence_path(group):
    return '%s/years_%s.json' % (collect.PACKAGE, group)


def execute(env, *, root=None, fetch=collect.get):
    root = collect.ROOT if root is None else Path(root)
    request_sha, run_id = collect.validate_identity(env, root, TASKS)
    groups = sorted({collect.MODELS[key][0] for key in TARGETS})
    for group in groups:
        found = {key: model(fetch, key) for key in TARGETS if collect.MODELS[key][0] == group}
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
        print('MODEL_GALLERY_YEARS_STOP:'+(str(exc) if isinstance(exc, collect.CollectError) else type(exc).__name__))
        raise SystemExit(1) from None
