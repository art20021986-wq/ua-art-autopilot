#!/usr/bin/env python3
"""Compose a scoped offline review candidate from an actual stable core capture.

No full-system-inventory, backup, writer-exclusion, Preview PASS, installation
authority, or current state beyond the observer's endpoints is claimed.
Private originals are supplied through explicit directories and never imported.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()


def read(path, expected=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('REGULAR_INPUT_REQUIRED:' + str(path))
    raw = path.read_bytes()
    if expected is not None and sha(raw) != expected:
        raise ValueError('INPUT_PIN_MISMATCH:' + str(path))
    return raw


def write_new(path, raw):
    path = Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if read(path) != raw:
        raise ValueError('OUTPUT_READBACK_MISMATCH')


def record(path, value):
    write_new(path, json.dumps(value, indent=2, sort_keys=True).encode() + b'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--current-core', type=Path, required=True)
    parser.add_argument('--expected-core-sha256', required=True)
    parser.add_argument('--expected-export-manifest-sha256', required=True)
    parser.add_argument('--observation-name', default='observation_summary.json')
    parser.add_argument('--private-inputs', type=Path, action='append', required=True)
    parser.add_argument('--routing-topology', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    repo, core, output, evidence = [p.resolve() for p in (args.repository, args.current_core, args.output, args.evidence)]
    if output.exists() or evidence.exists():
        raise ValueError('UNUSED_UNIQUE_OUTPUTS_REQUIRED')
    sys.dont_write_bytecode = True
    code_roots = [repo / 'cloud' / name for name in ('task088_price_sync', 'task088_stage3_renderer',
        'task088_autopilot_owner_policy', 'task088_v5_writer_fence')]
    code_pins = {str(p.relative_to(repo)):sha(read(p)) for directory in code_roots for p in directory.glob('*.py')}
    record(evidence / 'INTENT.json', {'reason':'Compose the final scoped point4 candidate from the newly observed current published rows, exact current core HTML, source/dependency pins and explicit module presence. Previous scoped checks are reused; no application suites or installation are run.',
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'expected_core_sha256':args.expected_core_sha256,
        'public_code_sha256':code_pins, 'script_sha256':sha(read(Path(__file__))), 'production_authority':False})
    raw_report = read(core / args.observation_name, args.expected_core_sha256)
    report = json.loads(raw_report)
    if report.get('contract') != 'PR114-POINT4-CORE-READONLY-OBSERVATION-1' or report.get('status') != 'PASS_CORE_DOUBLE_READ_STABLE_OBSERVATION' or report.get('export_completed') is not True:
        raise ValueError('REAL_SUCCESSFUL_CORE_OBSERVATION_REQUIRED')
    export_raw = read(core / 'export_manifest.json', args.expected_export_manifest_sha256)
    export = json.loads(export_raw)
    if report.get('plaintext_export') != export or export.get('format') != 'ONE_LINE_JSON_PARTS_UTF8':
        raise ValueError('TERMINAL_SUMMARY_EXPORT_BINDING_REQUIRED')
    exported = export.get('artifacts', {})
    if not exported or not export.get('parts') or not export.get('chunk_records'):
        raise ValueError('COMPLETE_EXPORT_ARTIFACT_MANIFEST_REQUIRED')
    for name,item in exported.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('BOUNDED_EXPORT_ARTIFACT_NAME_REQUIRED')
        raw = read(core / name, item['sha256'])
        if len(raw) != item['bytes']:
            raise ValueError('EXPORTED_ARTIFACT_SIZE_MISMATCH:' + name)
    embedded = json.loads(read(core / 'observation_summary.json'))
    expected_embedded = {key:value for key,value in report.items() if key != 'plaintext_export'}
    expected_embedded['export_completed'] = False
    if embedded != expected_embedded:
        raise ValueError('EMBEDDED_OBSERVATION_TERMINAL_SUMMARY_DISAGREEMENT')
    if (report.get('blockers') or report.get('quick_check') != 'ok' or report.get('legacy_UA_fallback_requires_review')
            or report.get('business_source_writes') is not False or report.get('business_SQL_writes') is not False
            or report.get('full_inventory_observed') is not False):
        raise ValueError('READ_ONLY_SCOPED_OBSERVATION_REQUIRED')
    stable = report.get('stability', {})
    if not stable or not all(value is True for value in stable.values()):
        raise ValueError('DOUBLE_READ_STABILITY_REQUIRED')
    if report.get('database') != report.get('second_database') or report.get('schema_sha256') != report.get('second_schema_sha256'):
        raise ValueError('EXACT_SECOND_DATABASE_READBACK_REQUIRED')
    rows = json.loads(read(core / 'published_price_rows.json'))
    fields = {'id', 'auto_number', 'published', 'status', 'price_uah', 'price_georgia'}
    if type(rows) is not list or any(type(row) is not dict or set(row) != fields or row.get('published') != 1 for row in rows):
        raise ValueError('EXACT_SIX_PUBLIC_IDENTITY_FIELDS_REQUIRED')
    if rows != report.get('published_rows') or sha(encoded(rows)) != report['database']['published_sha256']:
        raise ValueError('CURRENT_PUBLISHED_ROWS_BINDING_FAILED')
    codes = sorted(row['auto_number'] for row in rows)
    if any(type(code) is not str or not re.fullmatch(r'UA-[0-9]{4}', code) for code in codes) or codes != sorted(set(codes)) or codes != report['database']['published_codes']:
        raise ValueError('CURRENT_PUBLISHED_SET_BINDING_FAILED')
    expected_html = {folder + '/' + code + '.html' for folder in ('site', 'video') for code in codes}
    expected_html |= {folder + '/' + name + '.html' for folder in ('site', 'video') for name in ('index', 'katalog')}
    if set(report.get('core_html', {})) != expected_html or report.get('core_html_count') != len(expected_html):
        raise ValueError('EXACT_CURRENT_CORE_HTML_SET_REQUIRED')
    html = {name:read(core / name, item['sha256']) for name,item in report['core_html'].items()}
    if any(len(html[name]) != item['bytes'] for name,item in report['core_html'].items()):
        raise ValueError('CURRENT_CORE_HTML_SIZE_MISMATCH')
    if sha(encoded(report['core_html'])) != report['core_manifest_sha256']:
        raise ValueError('CURRENT_CORE_MANIFEST_MISMATCH')
    preserved_context = {}
    for section in ('diagnostic_html', 'supporting_html'):
        for name,item in report.get(section, {}).items():
            if item.get('exists') is False:
                continue
            raw = read(core / name, item['sha256'])
            if len(raw) != item['bytes']:
                raise ValueError('CONTEXT_HTML_SIZE_MISMATCH:' + name)
            preserved_context[name] = item
    def audit(event, values):
        if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'sqlite3.connect'):
            raise ValueError('OFFLINE_COMPOSITION_FORBIDDEN_EVENT:' + event)
    sys.addaudithook(audit)
    sys.path[:0] = [str(path) for path in code_roots]
    import install_package as engine
    from build_preflight_bundle import package_mapping
    from initial_html_prices import migrate_card, migrate_catalog
    input_pins = report['sources_dependencies_extra']
    if not (engine.SOURCES | engine.DEPENDENCIES) <= set(input_pins):
        raise ValueError('CURRENT_SOURCE_DEPENDENCY_OBSERVATION_INCOMPLETE')
    located = {}
    def private_input(name):
        expected = input_pins[name]['sha256']
        for directory in args.private_inputs:
            path = directory / name
            if path.is_file() and not path.is_symlink():
                raw = read(path)
                if sha(raw) == expected:
                    located[name] = {'path':str(path), 'sha256':expected, 'bytes':len(raw)}
                    return raw
        raise ValueError('EXACT_CURRENT_PRIVATE_INPUT_UNAVAILABLE:' + name)
    sources = {name:private_input(name) for name in engine.SOURCES}
    dependencies = {name:private_input(name) for name in engine.DEPENDENCIES}
    module_observation = report.get('runtime_modules')
    if type(module_observation) is not dict or set(module_observation) != engine.MODULES:
        raise ValueError('EXPLICIT_CURRENT_MODULE_PRESENCE_REQUIRED')
    if stable.get('runtime_modules_hashes_and_stamps') is not True:
        raise ValueError('MODULE_PRESENCE_DOUBLE_READ_REQUIRED')
    for name,item in module_observation.items():
        if type(item.get('exists')) is not bool:
            raise ValueError('EXPLICIT_MODULE_EXISTENCE_REQUIRED:' + name)
        if item['exists']:
            engine._hash(item.get('sha256'))
            if name in input_pins and input_pins[name]['sha256'] != item['sha256']:
                raise ValueError('CURRENT_SOURCE_MODULE_HASH_DISAGREEMENT:' + name)
    # Topology is separately evidenced. Current source pins are derived from
    # this observation, without asserting a new HTTP/static-mapping inspection.
    topology_raw = read(args.routing_topology)
    routing = json.loads(topology_raw)
    engine.validate_routing(routing)
    routing = dict(routing, source_sha256={name:item['sha256'] for name,item in report['routing_sources'].items()},
        offline_core_derivation={'topology_evidence_sha256':sha(topology_raw), 'core_observation_sha256':sha(raw_report),
            'new_HTTP_or_hosting_observation_by_builder':False})
    engine.validate_routing(routing)
    for name in ('site/index.html', 'video/index.html'):
        if report['core_html'][name]['sha256'] != routing['source_sha256'][name]:
            raise ValueError('HOME_ROUTING_CORE_PIN_MISMATCH')
    policy = {'site/index.html':'PROTECTED_LEGACY_NOT_SERVED'}
    mapping = package_mapping(repo)
    modules = {name:read(mapping[name]) for name in engine.MODULES}
    candidate = engine.build_candidates(sources, html, rows, modules, dependency_files=dependencies,
        homepage_policy=policy, routing=routing)
    if set(candidate) != engine.SOURCES | engine.MODULES | expected_html:
        raise ValueError('EXACT_SCOPED_CANDIDATE_FILE_SET_REQUIRED')
    compiled = sorted(engine.SOURCES | engine.MODULES)
    for name in compiled:
        compile(candidate[name], '<private-candidate-compile-only>', 'exec')
    # Independent per-file delta proof: price migration followed by the exact
    # known counter-client correction, with protected legacy home untouched.
    by_code = {row['auto_number']:row for row in rows}
    proofs = {}
    for name,raw in sorted(html.items()):
        text, code = raw.decode('utf-8'), Path(name).stem
        if code == 'index':
            priced, price_proof = engine.migrate_home_candidate(name, text, rows, policy, routing)
        elif code == 'katalog':
            priced, price_proof = migrate_catalog(text, rows)
        else:
            priced, price_proof = migrate_card(text, by_code[code])
        final, client_proof = engine.migrate_counter_client_candidate(name, priced,
            sources['ua_site_counters.py'], candidate['ua_site_counters.py'], policy)
        if final.encode('utf-8') != candidate[name] or price_proof.get('outside_price_unchanged') is not True or client_proof['unrelated_markup_preserved'] is not True:
            raise ValueError('HTML_APPROVED_DELTA_PROOF_FAILED:' + name)
        proofs[name] = {'before_sha256':sha(raw), 'after_sha256':sha(candidate[name]),
            'price_migration':price_proof, 'counter_client':client_proof,
            'outside_price_and_counter_client_unchanged':True,
            'all_bytes_unchanged':raw == candidate[name]}
    for relative,pin in code_pins.items():
        read(repo / relative, pin)
    before = {name:sha(raw) for name,raw in {**sources, **html}.items()}
    before.update({name:item['sha256'] if item['exists'] else None for name,item in module_observation.items()})
    manifest = engine.candidate_manifest(candidate, before)
    output.mkdir(mode=0o700)
    for name,raw in sorted(candidate.items()):
        write_new(output / name, raw)
    record(evidence / 'CANDIDATE_MANIFEST.json', {'contract':'PR114-CURRENT-CORE-OFFLINE-CANDIDATE-1',
        'files':manifest, 'candidate_manifest_sha256':sha(encoded(manifest)),
        'current_core_observation_sha256':sha(raw_report), 'installation_authority':False,
        'full_system_inventory_observed':False, 'writer_exclusion':False})
    record(evidence / 'HTML_DELTA_PROOFS.json', proofs)
    record(evidence / 'OFFLINE_ROUTING_INPUT.json', routing)
    record(evidence / 'PRESERVED_DIAGNOSTIC_SUPPORT_INPUTS.json', preserved_context)
    result = {'contract':'PR114-CURRENT-CORE-CANDIDATE-COMPOSITION-1', 'status':'PASS_SCOPED_CURRENT_CORE_COMPOSITION',
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(), 'private_candidate_directory':str(output),
        'candidate_manifest_sha256':sha(encoded(manifest)), 'candidate_files':len(candidate),
        'published_count':len(rows), 'published_codes':codes, 'source_count':len(sources),
        'module_count':len(modules), 'dependency_count':len(dependencies), 'core_html_count':len(html),
        'compile_count':len(compiled), 'compiled_without_execution':compiled,
        'html_approved_delta_proofs':len(proofs), 'counter_client_changed':sum(p['counter_client']['status'] == 'PATCHED_EXACT_SCRIPT' for p in proofs.values()),
        'protected_legacy_home_unchanged':candidate['site/index.html'] == html['site/index.html'],
        'core_observation_sha256':sha(raw_report), 'observer_stability':stable,
        'export_manifest_sha256':sha(export_raw), 'export_artifacts_verified':len(exported),
        'terminal_export_completed':True,
        'observation_started_at':report['started_at'], 'observation_finished_at':report['finished_at'],
        'private_input_bindings':located, 'public_code_sha256':code_pins, 'runtime_module_before_observation':module_observation,
        'dependency_sha256':{name:sha(raw) for name,raw in dependencies.items()},
        'preserved_diagnostic_support_count':len(preserved_context),
        'media_scope':'Observer metadata only; no media bytes were read by this builder.',
        'preview_gate':'NOT_ISSUED_CURRENT_RENDERING_REVIEW_SEPARATE', 'stage3_receipt':False, 'stage4_receipt':False,
        'production_written':False, 'full_system_inventory_observed':False, 'writer_exclusion':False,
        'installation_authority':False, 'historical_suites_rerun':False, 'script_sha256':sha(read(Path(__file__)))}
    record(evidence / 'RESULT.json', result)
    print(json.dumps({key:result[key] for key in ('status','candidate_files','published_count','compile_count',
        'html_approved_delta_proofs','counter_client_changed','candidate_manifest_sha256')}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(json.dumps({'status':'FAILED_NO_INSTALLATION','error_type':type(exc).__name__,'error':str(exc)}))
        raise SystemExit(1)
