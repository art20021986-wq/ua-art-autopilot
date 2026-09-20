#!/usr/bin/env python3
"""Apply one reviewed source-only delta to a verified offline current candidate.

This composes exact private sources with the canonical public source builder.
It never imports a private module, regenerates HTML, or grants install authority.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()


def read(path, expected=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('REGULAR_FILE_REQUIRED:' + str(path))
    raw = path.read_bytes()
    if expected is not None and sha(raw) != expected:
        raise ValueError('PIN_MISMATCH:' + str(path))
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
        raise ValueError('OUTPUT_READBACK_MISMATCH:' + str(path))


def record(path, value):
    write_new(path, json.dumps(value, sort_keys=True, indent=2).encode() + b'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, required=True)
    parser.add_argument('--previous-candidate', type=Path, required=True)
    parser.add_argument('--previous-evidence', type=Path, required=True)
    parser.add_argument('--previous-manifest-sha256', required=True)
    parser.add_argument('--previous-result-sha256', required=True)
    parser.add_argument('--expected-integrator-sha256', required=True)
    parser.add_argument('--expected-cars-sha256', required=True)
    parser.add_argument('--release-result', type=Path, required=True)
    parser.add_argument('--expected-release-result-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    repo = args.repository.resolve()
    old_root = args.previous_candidate.resolve()
    old_evidence = args.previous_evidence.resolve()
    output, evidence = args.output.resolve(), args.evidence.resolve()
    if output.exists() or evidence.exists():
        raise ValueError('UNUSED_UNIQUE_OUTPUTS_REQUIRED')
    sys.dont_write_bytecode = True
    old_manifest_raw = read(old_evidence / 'CANDIDATE_MANIFEST.json', args.previous_manifest_sha256)
    old_result_raw = read(old_evidence / 'RESULT.json', args.previous_result_sha256)
    previous = json.loads(old_manifest_raw)
    prior = json.loads(old_result_raw)
    manifest = previous['files']
    if len(manifest) != 68 or sha(encoded(manifest)) != previous['candidate_manifest_sha256']:
        raise ValueError('PREVIOUS_EXACT_68_MANIFEST_REQUIRED')
    if prior['candidate_manifest_sha256'] != previous['candidate_manifest_sha256']:
        raise ValueError('PREVIOUS_RESULT_MANIFEST_MISMATCH')
    if prior.get('status') != 'PASS_SCOPED_CURRENT_CORE_COMPOSITION':
        raise ValueError('SUCCESSFUL_PRIOR_CANONICAL_COMPOSITION_REQUIRED')
    old_files = {}
    for name, item in manifest.items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('RELATIVE_MANIFEST_PATH_REQUIRED')
        raw = read(old_root / name, item['after_sha256'])
        if len(raw) != item['bytes']:
            raise ValueError('PREVIOUS_CANDIDATE_SIZE_MISMATCH:' + name)
        old_files[name] = raw
    actual_files = {str(p.relative_to(old_root)) for p in old_root.rglob('*') if p.is_file()}
    if actual_files != set(manifest):
        raise ValueError('EXACT_PREVIOUS_CANDIDATE_TREE_REQUIRED')
    code_pins = {name:sha(read(repo / name)) for name in prior['public_code_sha256']}
    changed_public = {name:{'before_sha256':pin, 'after_sha256':code_pins[name]}
        for name,pin in prior['public_code_sha256'].items() if pin != code_pins[name]}
    integrator = 'cloud/task088_v5_writer_fence/integrate_private_sources.py'
    implementation_changes = {name for name in changed_public if not Path(name).name.startswith('test_')}
    if implementation_changes != {integrator} or code_pins[integrator] != args.expected_integrator_sha256:
        raise ValueError('ONLY_EXACT_REVIEWED_INTEGRATOR_IMPLEMENTATION_DELTA_ALLOWED')
    intent = {'reason':'A final review found the optional photo_hide import/register boundary before the missing-anchor gate. Recompose only canonical private sources; replace only cars_ui.py and prove the other 67 candidate files unchanged. Reuse all HTML generation and established checks.',
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'previous_candidate_manifest_sha256':previous['candidate_manifest_sha256'],
        'expected_integrator_sha256':args.expected_integrator_sha256,
        'expected_cars_sha256':args.expected_cars_sha256,
        'public_code_changes':changed_public, 'script_sha256':sha(read(Path(__file__))),
        'installation_authority':False, 'production_written':False}
    record(evidence / 'INTENT.json', intent)
    def audit(event, values):
        if event.startswith('socket.') or event in ('subprocess.Popen', 'os.system', 'sqlite3.connect'):
            raise ValueError('OFFLINE_COMPOSITION_FORBIDDEN_EVENT:' + event)
    sys.addaudithook(audit)
    code_roots = [repo / 'cloud' / name for name in ('task088_price_sync', 'task088_stage3_renderer',
        'task088_autopilot_owner_policy', 'task088_v5_writer_fence')]
    sys.path[:0] = [str(p) for p in code_roots]
    import install_package as engine
    from build_preflight_bundle import package_mapping
    bindings = prior['private_input_bindings']
    private = {name:read(item['path'], item['sha256']) for name,item in bindings.items()}
    sources = {name:private[name] for name in engine.SOURCES}
    dependencies = {name:private[name] for name in engine.DEPENDENCIES}
    if set(sources) | set(dependencies) != set(bindings):
        raise ValueError('UNCHANGED_EXACT_INPUT_SET_REQUIRED')
    composed = engine.build_source_candidates(sources, dependencies)
    if set(composed) != engine.SOURCES:
        raise ValueError('EXACT_SOURCE_COMPOSITION_REQUIRED')
    source_changes = sorted(name for name,raw in composed.items() if raw != old_files[name])
    if source_changes != ['cars_ui.py'] or sha(composed['cars_ui.py']) != args.expected_cars_sha256:
        raise ValueError('ONLY_EXACT_REVIEWED_CARS_OUTPUT_DELTA_ALLOWED')
    compile(composed['cars_ui.py'], '<private-candidate-compile-only>', 'exec')
    mapping = package_mapping(repo)
    for name in engine.MODULES:
        if read(mapping[name]) != old_files[name]:
            raise ValueError('RUNTIME_MODULE_CHANGE_NOT_ALLOWED:' + name)
    release_result_raw = read(args.release_result, args.expected_release_result_sha256)
    release_result = json.loads(release_result_raw)
    release_root = repo / 'cloud/task088_v5_install/release'
    release_provenance_raw = read(release_root / 'release_sources.json', release_result['provenance_sha256'])
    release_sources = json.loads(release_provenance_raw)['sources']
    if len(release_sources) != 20 or set(release_sources) != set(release_result['source_sha256']):
        raise ValueError('UNCHANGED_EXACT_20_PUBLIC_RELEASE_SOURCES_REQUIRED')
    for name,item in release_sources.items():
        pin = release_result['source_sha256'][name]
        if item['sha256'] != pin or read(repo / item['source_path'], pin) != read(release_root / name, pin):
            raise ValueError('PUBLIC_RELEASE_SOURCE_OR_OUTPUT_CHANGED:' + name)
    candidate = dict(old_files)
    candidate['cars_ui.py'] = composed['cars_ui.py']
    before = {name:item['before_sha256'] for name,item in manifest.items()}
    final_manifest = engine.candidate_manifest(candidate, before)
    changed_entries = sorted(name for name in manifest if final_manifest[name] != manifest[name])
    if changed_entries != ['cars_ui.py']:
        raise ValueError('ONLY_ONE_MANIFEST_ENTRY_MAY_CHANGE')
    unchanged = sorted(name for name in candidate if candidate[name] == old_files[name])
    if len(unchanged) != 67:
        raise ValueError('EXACT_67_UNCHANGED_REQUIRED')
    for relative,pin in code_pins.items():
        read(repo / relative, pin)
    output.mkdir(mode=0o700)
    for name,raw in sorted(candidate.items()):
        write_new(output / name, raw)
    for name in unchanged:
        if read(output / name) != read(old_root / name):
            raise ValueError('INDEPENDENT_UNCHANGED_READBACK_FAILED:' + name)
    final_wrapper = dict(previous, files=final_manifest,
        candidate_manifest_sha256=sha(encoded(final_manifest)),
        previous_candidate_manifest_sha256=previous['candidate_manifest_sha256'],
        source_only_delta='cars_ui.py')
    record(evidence / 'CANDIDATE_MANIFEST.json', final_wrapper)
    reused_evidence = {}
    for name in ('HTML_DELTA_PROOFS.json', 'OFFLINE_ROUTING_INPUT.json', 'PRESERVED_DIAGNOSTIC_SUPPORT_INPUTS.json'):
        raw = read(old_evidence / name)
        write_new(evidence / name, raw)
        reused_evidence[name] = {'sha256':sha(raw), 'previous_path':str(old_evidence / name), 'bytes_unchanged':True}
    result = {'contract':'PR114-CURRENT-CORE-SOURCE-DELTA-1', 'status':'PASS_EXACT_ONE_SOURCE_DELTA_67_UNCHANGED',
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
        'private_candidate_directory':str(output), 'candidate_files':len(candidate),
        'candidate_manifest_sha256':sha(encoded(final_manifest)),
        'previous_candidate_directory':str(old_root),
        'previous_candidate_manifest_sha256':previous['candidate_manifest_sha256'],
        'previous_manifest_file_sha256':sha(old_manifest_raw), 'previous_result_sha256':sha(old_result_raw),
        'changed_files':{'cars_ui.py':{'previous_after_sha256':manifest['cars_ui.py']['after_sha256'],
            **final_manifest['cars_ui.py']}}, 'unchanged_files':unchanged, 'unchanged_files_count':67,
        'readback_files':68, 'canonical_source_composition_count':len(composed),
        'compile_count_this_delta':1, 'compiled_without_execution':['cars_ui.py'],
        'unchanged_python_compile_credits_retained':19, 'runtime_modules_unchanged':len(engine.MODULES),
        'source_inputs_unchanged':len(sources), 'dependency_inputs_unchanged':len(dependencies),
        'private_input_bindings':bindings, 'public_code_sha256':code_pins, 'public_code_changes':changed_public,
        'core_observation_sha256':prior['core_observation_sha256'],
        'core_observation_interval':{'started_at':prior['observation_started_at'], 'finished_at':prior['observation_finished_at']},
        'current_runtime_state_claim':False, 'html_regenerated':False, 'html_bytes_unchanged':48,
        'reused_evidence':reused_evidence, 'historical_suites_rerun':False, 'tests_rerun':False,
        'public_release_refresh_required':False, 'installation_authority':False, 'production_written':False,
        'public_release_unchanged_files':20, 'public_release_result_sha256':sha(release_result_raw),
        'public_release_provenance_sha256':sha(release_provenance_raw),
        'full_system_inventory_observed':False, 'writer_exclusion':False,
        'preview_gate':'NOT_ISSUED_CURRENT_RENDERING_REVIEW_SEPARATE', 'stage3_receipt':False, 'stage4_receipt':False,
        'script_sha256':sha(read(Path(__file__)))}
    record(evidence / 'RESULT.json', result)
    print(json.dumps({key:result[key] for key in ('status','candidate_files','candidate_manifest_sha256',
        'unchanged_files_count','html_regenerated','runtime_modules_unchanged')}))


if __name__ == '__main__':
    main()
