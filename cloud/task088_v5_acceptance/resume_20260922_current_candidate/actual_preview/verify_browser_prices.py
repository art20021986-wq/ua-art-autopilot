"""Validate recorded DOM observations against the actual captured CRM rows.

This is scoped evidence, never installation authority or a full Preview gate.
"""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
capture = json.loads((root.parent / 'pr114-offline/current_core_capture/summary.json').read_bytes())
manifest = json.loads((root / 'manifest.json').read_bytes())
applicability = json.loads((root.parent / 'pr114-offline/current_candidate_evidence/PREVIEW_APPLICABILITY.json').read_bytes())
observations = json.loads((root / 'browser_cases.json').read_bytes())
latest = {(o['path'], o['requested_language_button'], o['viewport_name']): o for o in observations}
rows = {r['auto_number']: r for r in capture['published_rows']}
results = []
pending = []
for case in applicability['mandatory_affected_browser_matrix']:
    key = case['path'], case['language'], case['viewport']
    o = latest[key]
    assert o['candidate_sha256'] == manifest['files'][key[0]]['sha256'], key
    assert o['language'] == {'RU': 'ru', 'UA': 'uk', 'GE': 'ka'}[key[1]], key
    ready = o['ready_state'] == 'complete' and o['fonts_status'] == 'loaded'
    assert o['exact_dimensions'] and o['viewport_media_match'], key
    assert o['document_scroll_width'] <= o['document_width'], key
    expected = set(rows) if key[0].endswith('katalog.html') else ({Path(key[0]).stem} if '/UA-' in key[0] else set())
    assert {p['car'] for p in o['prices']} == expected, key
    for p in o['prices']:
        r = rows[p['car']]
        markets = ['ukraine'] if r['status'] == 'ua_arrived' else ['ukraine', 'georgia']
        assert [v['market'] for v in p['rows']] == markets, (key, p['car'])
        for v in p['rows']:
            value = r['price_uah' if v['market'] == 'ukraine' else 'price_georgia']
            assert v['value'] == ('' if value is None else str(value)), (key, p['car'])
            if value is None:
                assert {'RU': 'Цена уточняется', 'UA': 'Ціна уточнюється', 'GE': 'ფასი ზუსტდება'}[key[1]] in v['text'], key
            box = v['box']
            assert box['width'] > 0 and box['height'] > 0, key
            assert box['x'] >= -1 and box['x'] + box['width'] <= o['document_width'] + 1, key
        if len(p['rows']) == 2:
            a, b = (v['box'] for v in p['rows'])
            assert b['y'] >= a['y'] + a['height'] - 1, key
    result = {'path':key[0], 'language':key[1], 'viewport':key[2], 'observed_at':o['observed_at'],
              'status':'PASS_SCOPED_DOM_PRICE_LAYOUT' if ready else 'FINAL_LOAD_RECHECK_PENDING',
              'ready_state':o['ready_state'], 'fonts_status':o['fonts_status']}
    (results if ready else pending).append(result)
report = {'contract':'PR114-ACTUAL-BROWSER-PRICE-LAYOUT-1', 'status':'PASS_SCOPED_48_CASES' if not pending else 'INCOMPLETE_FINAL_LOAD_RECHECK', 'cases':results, 'pending':pending,
    'raw_observations':len(observations), 'raw_sha256':hashlib.sha256((root/'browser_cases.json').read_bytes()).hexdigest(),
    'candidate_manifest_sha256':'95d0b4a11b1ada311c384a2cbe213b6b58ae1da540f61b640c5effecf0fb3b8e',
    'preview_resource_manifest_sha256':hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest(),
    'full_preview_gate':'NOT_ISSUED', 'production_written':False,
    'limitations':['CSS viewport in cloud Chrome; no mobile OS or touch emulation',
                    'Lazy images outside view are not asserted decoded',
                    'Full inventory, current canonical preflight, writer exclusion, verified backup and installation authority remain separate gates']}
(root/'BROWSER_PRICE_LAYOUT_RESULT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':report['status'],'cases':len(results),'pending':len(pending),'raw_observations':len(observations)}))
