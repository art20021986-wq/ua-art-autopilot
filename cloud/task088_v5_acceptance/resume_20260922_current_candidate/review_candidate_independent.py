#!/usr/bin/env python3
"""Independent current-capture candidate byte/semantic review; no deployment."""
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import zipfile

sys.dont_write_bytecode = True


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()


class Markets(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.car = None
        self.blocks = {}
        self.components = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'ua-market-prices-v1' in attrs.get('class', '').split():
            self.car = attrs['data-ua-car']
            self.components.append(self.car)
        if 'data-ua-market' in attrs:
            key = (self.car, attrs['data-ua-market'])
            assert key not in self.blocks, ('duplicate_market', key)
            self.blocks[key] = {k: attrs[k] for k in ('data-ua-field', 'data-ua-value', 'data-ua-currency')}


def main():
    parser = argparse.ArgumentParser()
    for name in ('repository', 'capture', 'candidate', 'evidence', 'private-inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--package', type=Path)
    args = parser.parse_args()
    for root in ('task088_stage3_renderer', 'task088_price_sync', 'task088_autopilot_owner_policy', 'task088_v5_writer_fence'):
        sys.path.insert(0, str(args.repository / 'cloud' / root))
    import install_package as engine
    from build_preflight_bundle import package_mapping
    from initial_html_prices import migrate_card, migrate_catalog

    obs_raw = (args.capture / 'summary.json').read_bytes()
    assert sha(obs_raw) == '07e07f499c20d5db62e0ae58cb4922be2cfacd4e8956879dbcd374322bb71454'
    obs = json.loads(obs_raw)
    rows = json.loads((args.capture / 'published_price_rows.json').read_bytes())
    assert rows == obs['published_rows'] and sha(encoded(rows)) == obs['database']['published_sha256']
    by_code = {r['auto_number']: r for r in rows}
    assert len(rows) == len(by_code) == 21 and 'UA-0002' not in by_code
    assert by_code['UA-0018']['price_uah'] == 22900
    assert by_code['UA-0010']['price_georgia'] == 8750
    metadata = json.loads((args.evidence / 'CANDIDATE_MANIFEST.json').read_bytes())
    manifest = metadata['files']
    assert metadata['current_core_observation_sha256'] == sha(obs_raw)
    assert metadata['candidate_manifest_sha256'] == sha(encoded(manifest))
    candidate = {n: (args.candidate / n).read_bytes() for n in manifest}
    assert len(manifest) == 66
    assert set(manifest) == engine.SOURCES | engine.MODULES | set(obs['core_html'])
    for name, raw in candidate.items():
        assert manifest[name]['after_sha256'] == sha(raw) and manifest[name]['bytes'] == len(raw), name
        if name in obs['core_html']:
            before = obs['core_html'][name]['sha256']
        elif name in engine.MODULES:
            item = obs['runtime_modules'][name]
            before = item['sha256'] if item['exists'] else None
        else:
            before = obs['sources_dependencies_extra'][name]['sha256']
        assert manifest[name]['before_sha256'] == before, ('true_before_image', name)

    sources = {n: (args.private_inputs / n).read_bytes() for n in engine.SOURCES}
    dependencies = {n: (args.private_inputs / n).read_bytes() for n in engine.DEPENDENCIES}
    for name, raw in {**sources, **dependencies}.items():
        assert sha(raw) == obs['sources_dependencies_extra'][name]['sha256'], name
    generated_sources = engine.build_source_candidates(sources, dependencies)
    assert generated_sources == {n: candidate[n] for n in engine.SOURCES}
    mapping = package_mapping(args.repository)
    for name in engine.MODULES:
        assert candidate[name] == Path(mapping[name]).read_bytes(), name

    routing = json.loads((args.evidence / 'OFFLINE_ROUTING_INPUT.json').read_bytes())
    policy = {'site/index.html': 'PROTECTED_LEGACY_NOT_SERVED'}
    checked_html = []
    components = markets = missing_ge = ge_values = 0
    # Value is pinned independently, never copied from builder output.
    original_catalog_sha = '279a221536aecd36111d496482f1bbf8594f38ed7cc19fb77561faed27fc6d01'
    for name in sorted(obs['core_html']):
        raw = (args.capture / name).read_bytes()
        assert sha(raw) == obs['core_html'][name]['sha256'], name
        source = raw.decode()
        code = Path(name).stem
        if code == 'katalog':
            assert sha(raw) == original_catalog_sha
            articles = list(re.finditer(r'<article\b[^>]*class="catalog-card"[^>]*>.*?</article>', source, re.S))
            target = [m for m in articles if set(re.findall(r'UA-[0-9]{4,}', m[0])) == {'UA-0018'}]
            assert len(articles) == 21 and len(target) == 1
            exact = '<b data-ru="19 900 $" data-uk="19 900 $">19 900 $</b>'
            assert target[0][0].count(exact) == 1
            at = target[0].start() + target[0][0].index(exact)
            prepared = source[:at] + '<b data-ru="22 900 $" data-uk="22 900 $">22 900 $</b>' + source[at + len(exact):]
            migrated, _ = migrate_catalog(prepared, rows)
        elif code == 'index':
            migrated, _ = engine.migrate_home_candidate(name, source, rows, policy, routing)
        else:
            migrated, _ = migrate_card(source, by_code[code])
        final, _ = engine.migrate_counter_client_candidate(name, migrated, sources['ua_site_counters.py'], candidate['ua_site_counters.py'], policy)
        assert final.encode() == candidate[name], ('independent_exact_derivation', name)
        parsed = Markets(candidate[name].decode())
        selected = rows if code == 'katalog' else [] if code == 'index' else [by_code[code]]
        assert sorted(parsed.components) == sorted(r['auto_number'] for r in selected), name
        expected = {}
        for row in selected:
            car = row['auto_number']
            expected[(car, 'ukraine')] = {'data-ua-field': 'price_uah', 'data-ua-value': str(row['price_uah']), 'data-ua-currency': 'USD'}
            if not row['status'].startswith('ua_'):
                expected[(car, 'georgia')] = {'data-ua-field': 'price_georgia', 'data-ua-value': str(row['price_georgia']) if row['price_georgia'] is not None else '', 'data-ua-currency': 'USD'}
        assert parsed.blocks == expected, ('actual_crm_market_semantics', name)
        components += len(parsed.components)
        markets += len(parsed.blocks)
        missing_ge += sum(k[1] == 'georgia' and v['data-ua-value'] == '' for k, v in parsed.blocks.items())
        ge_values += sum(k[1] == 'georgia' and v['data-ua-value'] == '8750' for k, v in parsed.blocks.items())
        checked_html.append(name)
    assert (components, markets, missing_ge, ge_values) == (84, 148, 60, 4)
    package_review = None
    if args.package:
        with zipfile.ZipFile(args.package) as z:
            package = json.loads(z.read('package_manifest.json'))
            expected = {'package_manifest.json', 'public/ua/a.js', 'evidence/ua-a-js.json'}
            expected |= {'candidate/' + n for n in obs['core_html']}
            expected |= {'runtime/' + n for n in package['runtime_sha256']}
            assert len(z.namelist()) == len(set(z.namelist())) == 54 and set(z.namelist()) == expected
            assert package['observer_sha256'] == sha(obs_raw)
            assert package['canonical_candidate_manifest_sha256'] == metadata['candidate_manifest_sha256']
            assert package['candidate_manifest_evidence_sha256'] == sha((args.evidence / 'CANDIDATE_MANIFEST.json').read_bytes())
            assert package['published_codes'] == obs['database']['published_codes']
            assert package['browser_run'] is False and package['preview_gate'] == 'NOT_PASSED'
            for name in obs['core_html']:
                assert z.read('candidate/' + name) == candidate[name]
                assert package['candidate_html_sha256'][name] == sha(candidate[name])
            for name, pin in package['runtime_sha256'].items():
                raw = z.read('runtime/' + name)
                assert sha(raw) == pin and raw == (args.repository / 'cloud/task088_v5_preview' / name).read_bytes()
            package_review = {'sha256': sha(args.package.read_bytes()), 'members': 54, 'html': 46, 'private_sources_included': False}
    result = {'status': 'PASS_INDEPENDENT_CURRENT_CANDIDATE_BYTES_AND_SEMANTICS_ONLY', 'candidate_manifest_sha256': metadata['candidate_manifest_sha256'], 'observer_sha256': sha(obs_raw), 'candidate_files_verified': 66, 'html_independently_reconstructed': len(checked_html), 'current_car_components': components, 'market_blocks': markets, 'missing_ge_placeholders': missing_ge, 'ge_8750_blocks': ge_values, 'true_original_before_images_verified': True, 'UA0018_current_22900_preserved': True, 'UA0002_not_in_rendered_car_inventory': True, 'package_review': package_review, 'browser_run': False, 'preview_pass': False, 'installation_authority': False, 'production_preflight_reconciliation_support': 'SEPARATELY_REQUIRED', 'script_sha256': sha(Path(__file__).read_bytes())}
    with args.output.open('x') as f:
        json.dump(result, f, sort_keys=True, indent=2)
        f.write('\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
