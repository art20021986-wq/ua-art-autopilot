#!/usr/bin/env python3
"""Read-only current Preview applicability check, never an acceptance receipt.

Checks captured bytes and exact candidate outputs, computes only the affected
browser matrix, and preserves historical evidence without redating it. Core-only
observations cannot prove full inventory equality or resource/runtime binding.
No private application module is imported; only public pure HTML patchers run.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
from pathlib import Path
import re
from html.parser import HTMLParser
from datetime import datetime, timezone


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode()


def read(path):
    path = Path(path).absolute()
    if path.resolve(strict=True) != path or not path.is_file() or path.stat().st_size > 32*1024*1024:
        raise ValueError('REGULAR_BOUNDED_NONSYMLINK_INPUT_REQUIRED:' + str(path))
    return path.read_bytes()


def load(path):
    return json.loads(read(path))


def located(root, name, candidates):
    found = [root / prefix / name for prefix in candidates if (root / prefix / name).is_file()]
    if len(found) != 1:
        raise ValueError('ONE_EXACT_FILE_REQUIRED:' + name)
    return found[0]


def inert_counter_equivalence(after, before_script, after_script, historical_sha):
    """A card with no sync entrypoint cannot reach the changed classifier.

    Exact inverse of the reviewed literal replacement must recover the historic
    whole-page digest. Other JS/CSS/markup mentioning either entrypoint fails the
    exemption. This is not a blanket exception for changed inline scripts.
    """
    source = after.decode()
    found = [m for m in re.finditer(r'<script\b[^>]*>(.*?)</script\s*>',source,re.I|re.S)
             if m.group(1).strip() == after_script.strip()]
    if len(found) != 1:
        return False
    match = found[0]
    remainder = source[:match.start()] + source[match.end():]
    if any(token in remainder for token in ('catalog-grid','outline-cta')):
        return False
    body = match.group(1)
    start = match.start(1) + len(body) - len(body.lstrip())
    inverse = source[:start] + before_script.strip() + source[start+len(after_script.strip()):]
    return sha(inverse.encode()) == historical_sha


def current_metadata_only(old, new, code):
    """Bounded current operator metadata, never a historical value acceptance.

    Return-link cachebuster and footer timestamp are presentation metadata.
    A naturally elapsed one/two-digit countdown/plural remains current input;
    only unchanged UI regions can inherit old acceptance, not its new value.
    """
    patterns = {
        'catalog_cache_buster':r"(?<=<a class='vtoraya' href='katalog.html\?v=)\d+(?='>← Все машины</a>)",
        'footer_timestamp':r'(?<=UA ART COMPANY LLC · '+re.escape(code)+r"<br>обновлено )\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}(?=<div class='avtor'>)",
    }
    changes = {}
    left, right = old.decode(), new.decode()
    for key,pattern in patterns.items():
        a,b = re.findall(pattern,left),re.findall(pattern,right)
        if len(a) != 1 or len(b) != 1:
            return None
        changes[key] = {'before':a[0],'current':b[0]}
        left,right = re.sub(pattern,'<' + key + '>',left),re.sub(pattern,'<' + key + '>',right)
    day = r'(?<=<span class="ua-stage-v1-days">)[0-9]{1,2}(?=</span>)'
    plural = r'(?<=<span class="ua-stage-v1-days-copy">)д(?:ень|ня|ней)(?= до выдачи<br>в Киеве</span>)'
    a,b = re.findall(day,left),re.findall(day,right)
    if a or b:
        pa,pb = re.findall(plural,left),re.findall(plural,right)
        if len(a) != 1 or len(b) != 1 or len(pa) != 1 or len(pb) != 1:
            return None
        if int(b[0]) > int(a[0]):
            return None
        stamps = changes['footer_timestamp']
        elapsed = (datetime.strptime(stamps['current'],'%d.%m.%Y %H:%M').date() -
                   datetime.strptime(stamps['before'],'%d.%m.%Y %H:%M').date()).days
        def day_word(n):
            return 'день' if n % 10 == 1 and n % 100 != 11 else 'дня' if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else 'дней'
        if int(a[0])-int(b[0]) != elapsed or pa[0] != day_word(int(a[0])) or pb[0] != day_word(int(b[0])):
            return None
        changes['current_countdown_preserved_not_historically_accepted'] = {'before':a[0]+' '+pa[0],'current':b[0]+' '+pb[0]}
        left,right = re.sub(day,'<countdown>',left),re.sub(day,'<countdown>',right)
        left,right = re.sub(plural,'<countdown_plural>',left),re.sub(plural,'<countdown_plural>',right)
    if left != right or 'ua-site-counters-123' in left:
        return None
    return {'status':'UNCHANGED_UI_REGIONS_ONLY_CURRENT_METADATA_PRESERVED','changes':changes,
            'normalized_sha256':sha(left.encode()),'css_inline_scripts_market_vin_spec_gallery_unchanged':True,
            'countdown_business_correctness_reestablished':False}


def evaluate(args):
    repo, capture, candidate = [Path(v).resolve(strict=True) for v in (args.repository, args.capture, args.candidate)]
    oldroot = repo / 'cloud/task088_v5_acceptance'
    gatepath = oldroot / 'resume_20260915_2/PREVIEW_GATE.json'
    bindingpath = oldroot / 'resume_20260914/canonical/PREFLIGHT_BROWSER_BINDING_V2.json'
    gate, binding, obs = load(gatepath), load(bindingpath), load(args.observer)
    expected_stability = {'database_and_published_rows','source_hashes_and_stamps','routing_hashes_and_stamps',
        'core_html_hashes_and_stamps','diagnostic_hashes_and_stamps','supporting_html_hashes_and_stamps',
        'runtime_modules_hashes_and_stamps','known_runtime_source_overlap','referenced_media_metadata_only','home_routing_equal_core'}
    if (obs.get('contract') != 'PR114-POINT4-CORE-READONLY-OBSERVATION-1' or
            obs.get('status') != 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION' or obs.get('export_completed') is not True or
            obs.get('blockers') or set(obs.get('stability',{})) != expected_stability or
            not all(value is True for value in obs['stability'].values()) or
            obs.get('database') != obs.get('second_database') or obs.get('schema_sha256') != obs.get('second_schema_sha256')):
        raise ValueError('COMPLETE_TERMINAL_CORE_OBSERVATION_REQUIRED_NOT_EMBEDDED_PREEXPORT_SUMMARY')
    if sha(read(gatepath)) != '3ed070183d19de801348aef5a521d30781c6528aa585441c6593ab34ae7f864a':
        raise ValueError('IMMUTABLE_HISTORICAL_GATE_PIN_MISMATCH')
    if binding['installation_candidate_manifest_sha256'] != gate['candidate_manifest_sha256']:
        raise ValueError('HISTORICAL_CANDIDATE_BRIDGE_MISMATCH')
    rows = load(capture / 'published_price_rows.json')
    rows = sorted(rows, key=lambda r: r['auto_number'])
    codes = [r['auto_number'] for r in rows]
    if (not codes or len(codes) != len(set(codes)) or
            any(not re.fullmatch(r'UA-[0-9]{4,}', c) for c in codes) or
            rows != sorted(obs['published_rows'], key=lambda r:r['auto_number'])):
        raise ValueError('EXACT_OBSERVED_PUBLISHED_ROWS_REQUIRED')
    identity = [{k:r.get(k) for k in ('id','auto_number','published','status','price_uah','price_georgia')} for r in obs['published_rows']]
    if sha(encoded(identity)) != obs['database']['published_sha256'] or codes != obs['database']['published_codes']:
        raise ValueError('INDEPENDENT_OBSERVED_PUBLISHED_IDENTITY_MISMATCH')
    names = sorted(f'{prefix}/{name}.html' for prefix in ('site','video') for name in ['index','katalog',*codes])
    sys.path[:0] = [str(repo/'cloud/task088_stage3_renderer'), str(Path(__file__).resolve().parent)]
    from bound_catalog_reconciliation import reconcile_catalogs
    reconciliation_adapter = Path(__file__).resolve().parent/'bound_catalog_reconciliation.py'
    reconciliation_adapter_sha256 = sha(read(reconciliation_adapter))
    prepared_html, reconciliation = reconcile_catalogs(
        {name:read(located(capture,name,('','public_html'))) for name in names},
        obs['published_rows'], read(args.observer))
    if set(obs.get('core_html', {})) != set(names):
        raise ValueError('COMPLETE_DYNAMIC_CORE_HTML_OBSERVATION_REQUIRED')
    if sha(encoded(obs['core_html'])) != obs.get('core_manifest_sha256'):
        raise ValueError('OBSERVER_CORE_MANIFEST_DIGEST_MISMATCH')
    public_paths = [repo/'cloud/task088_stage3_renderer'/n for n in ('initial_html_prices.py','uaart_market_prices.py')]
    public_paths += [repo/'cloud/task088_price_sync/patch_site_counters.py']
    public_pins = {str(p.relative_to(repo)):sha(read(p)) for p in public_paths}
    sys.path[:0] = [str(repo/'cloud/task088_stage3_renderer'), str(repo/'cloud/task088_price_sync')]
    from initial_html_prices import migrate_card, migrate_catalog, migrate_home
    from patch_site_counters import patch_html_client, patch_source, _client_literal
    counter_before = read(args.before_counter_source).decode()
    if sha(counter_before.encode()) != obs['sources_dependencies_extra']['ua_site_counters.py']['sha256']:
        raise ValueError('COUNTER_SOURCE_NOT_BOUND_TO_CURRENT_OBSERVATION')
    counter_after = patch_source(counter_before)
    before_script, after_script = _client_literal(counter_before), _client_literal(counter_after)
    oldhashes = {e['path']: e['retained_harness_sha256'] for e in binding['served_pages_compared'] if e['matches']}
    rowby = {r['auto_number']:r for r in rows}
    pages, affected, retained, counter_provisional, metadata_retained = [], [], [], [], []
    for name in names:
        before = read(located(capture, name, ('','public_html')))
        if sha(before) != obs['core_html'][name]['sha256'] or len(before) != obs['core_html'][name]['bytes']:
            raise ValueError('CAPTURE_NOT_BOUND:' + name)
        exported = obs['plaintext_export']['artifacts'].get(name)
        if not exported or exported['sha256'] != sha(before) or exported['bytes'] != len(before):
            raise ValueError('CAPTURE_EXPORT_TERMINAL_MANIFEST_MISMATCH:'+name)
        after = read(located(candidate, name, ('', 'public' if name.startswith('video/') else 'offline')))
        source = prepared_html[name].decode()
        basename = Path(name).stem
        if name == 'site/index.html':
            migrated, protection = source, {'outside_price_unchanged':True}
        elif basename == 'index':
            migrated, protection = migrate_home(source, rows)
        elif basename == 'katalog':
            migrated, protection = migrate_catalog(source, rows)
        else:
            migrated, protection = migrate_card(source, rowby[basename])
        # Legacy site/index is preserved even when it has an old counter script.
        if name != 'site/index.html':
            migrated, counter = patch_html_client(migrated, counter_before, counter_after)
        else:
            counter = {'status':'UNSERVED_LEGACY_PRESERVED'}
        if migrated.encode() != after or not protection.get('outside_price_unchanged'):
            raise ValueError('EXACT_SCOPED_CANDIDATE_HTML_MISMATCH:' + name)
        old = oldhashes.get('/'+name)
        inert = bool(old and basename in rowby and inert_counter_equivalence(after,before_script,after_script,old))
        metadata = None
        if old and basename in rowby and args.historical_candidate:
            historic = read(located(Path(args.historical_candidate).resolve(strict=True),name,('','public')))
            if sha(historic) != old:
                raise ValueError('HISTORICAL_CANDIDATE_BYTES_NOT_BOUND_TO_RETAINED_HARNESS:'+name)
            metadata = current_metadata_only(historic,after,basename)
        item = {'path':'/'+name, 'before_sha256':sha(before), 'after_sha256':sha(after),
                'intermediate_before_strict_migration_sha256':sha(prepared_html[name]),
                'catalog_reconciliation':reconciliation['pages'].get(name),
                'counter_client':counter['status'], 'historical_harness_sha256':old,
                'all_unrelated_markup_preserved':True, 'historical_page_bytes_equal':old == sha(after),
                'historical_render_equivalent_inert_counter_literal_only':inert,
                'bounded_current_metadata_delta':metadata}
        pages.append(item)
        if name.startswith('video/'):
            (retained if old == sha(after) else metadata_retained if metadata else counter_provisional if inert else affected).append('/'+name)
    stable = obs.get('status') in ('PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION', 'PASS_DOUBLE_READ_STABLE_OBSERVATION')
    blockers = []
    if not stable:
        blockers.append('CURRENT_OBSERVER_NOT_COMPLETE_STABLE')
    blockers += ['CURRENT_PREVIEW_RUNTIME_AND_REFERENCED_RESOURCES_BINDING_REQUIRED',
                 'AFFECTED_REAL_BROWSER_EVIDENCE_REQUIRED',
                 'CHANGED_SOURCE_GENERATION_AND_INDEPENDENT_REVIEW_REQUIRED']
    if any(sha(read(repo/name)) != pin for name,pin in public_pins.items()):
        raise ValueError('PUBLIC_PURE_PATCHER_CHANGED_DURING_CHECK')
    if sha(read(reconciliation_adapter)) != reconciliation_adapter_sha256:
        raise ValueError('RECONCILIATION_ADAPTER_CHANGED_DURING_CHECK')
    return {
        'contract':'PR114-CURRENT-PREVIEW-APPLICABILITY-CHECK-1',
        'reconciliation_adapter_sha256':reconciliation_adapter_sha256,
        'catalog_reconciliation':reconciliation,
        'status':'OFFLINE_CORE_CHECKS_PASS_BROWSER_AND_RESOURCE_BINDING_PENDING' if stable else 'BLOCKED',
        'evaluated_at':datetime.now(timezone.utc).isoformat(),
        'historical_gate':{'path':str(gatepath),'sha256':sha(read(gatepath)),'evaluated_at':gate['evaluated_at'],
                           'status_preserved':gate['status'],'criteria':list(gate['checks'])},
        'observer':{'path':str(args.observer),'sha256':sha(read(args.observer)), 'status':obs.get('status'),
                    'finished_at':obs.get('finished_at'), 'full_inventory_observed':obs.get('full_inventory_observed',False)},
        'published_count':len(codes), 'published_codes':codes,
        'database':obs['database'],'schema_sha256':obs['schema_sha256'],
        'public_pure_patcher_sha256':public_pins,
        'stage_codes':{s:[r['auto_number'] for r in rows if r['status']==s] for s in sorted({r['status'] for r in rows})},
        'core_pages':pages,
        'eligible_historical_page_retention_pending_resource_runtime_binding':retained,
        'eligible_unchanged_ui_retention_with_current_metadata_preserved':metadata_retained,
        'current_metadata_retention_scope':'Unchanged CSS/scripts/market/VIN/spec/gallery only, conditioned on referenced-resource binding. Current timestamps/cachebusters/countdown values are preserved current observations and are not re-labelled historical PASS.',
        'counter_literal_only_pages_pending_independent_reachability_proof':counter_provisional,
        'counter_literal_only_scope_requirement':'Exact inverse restores historical page SHA. Before omitting these browser cases, independently prove decoded DOM and bound external/inline scripts cannot reach catalog-grid or outline-cta entrypoints. Raw token absence alone is not that proof.',
        'mandatory_affected_browser_pages':affected,
        'mandatory_affected_browser_matrix':[{'path':p,'language':lang,'viewport':size,'status':'NOT_RUN'}
             for p in affected for lang in ('RU','UA','GE') for size in ('desktop','mobile')],
        'conditional_browser_matrix_unless_counter_scope_proved':[{'path':p,'language':lang,'viewport':size,'status':'PENDING_SCOPE_PROOF_OR_REAL_BROWSER'}
             for p in counter_provisional for lang in ('RU','UA','GE') for size in ('desktop','mobile')],
        'offline_assertions':['actual capture hashes match independent observer','all current rows match independent DB identity',
             'all dynamic 2N+4 core HTML match exact price migration plus bounded counter client patch',
             'unrelated HTML preserved relative to current operator data','legacy site/index bytes preserved'],
        'not_asserted':['full inventory equality','browser rendering','resource decoding','current hosting mappings',
             'runtime worker binding','writer exclusion','publication','Stage3','Stage4','Preview24/24'],
        'blockers':blockers, 'preview_gate':'NOT_PASSED', 'browser_run':False,'production_written':False,
        'historical_tests_rerun':False,'script_sha256':sha(read(__file__))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repository','observer','capture','candidate','before-counter-source','output'):
        parser.add_argument('--'+name, required=True)
    parser.add_argument('--historical-candidate')
    args = parser.parse_args()
    result = evaluate(args)
    with open(args.output, 'x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status':result['status'],'affected_browser_cases':len(result['mandatory_affected_browser_matrix']),
                      'eligible_retained_pages':len(result['eligible_historical_page_retention_pending_resource_runtime_binding']),
                      'output':args.output}))


if __name__ == '__main__':
    main()
