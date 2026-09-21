"""Build an isolated, source-bound candidate. Never install or activate it."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SCHEMA_SHA = '1d5aacc240cc0e330ae059bf56e32a3ce50200ee1bfe08da8834ae4f98c0480a'
UNCHANGED = {
    'db.py': 'b732a5c731d85cb4c9b1cfddb2fc20961b75230d64e29563a5b5ac328d62c086',
    'run_all.py': 'cc996b82b00fdfd9c95348193cd1d31b7d0a44bc1601fbb0b85b0c561ccb0fa9',
    'start_safe.py': '21aded2b576b36c6cea84b431c691b22eb09105ca5ec13bb6fd0910452c2cbeb',
    'publication_fence.py': 'c739a1017c53c6391dbf875621d6c860216fe8a132b738eef47b8f8019594a21',
    'ua_site_counters.py': '500ca67145faa38ca9f72ac6da85e2a7d1c351f8f2fcca4a2edeb34c22734c23',
    'ua_crm_catalog_folders.py': '63cfe41b4ce4d6e5c1f5615235da8cad50c40fde3278a799a82dfae410daf7b0',
    'ua_stage_catalog_sync.py': 'c349d44821f92950234705d41507587c3ca2780dd750abda0028c060569a5beb',
    'ua_additional_spec.py': '6d2ab7b2bace29b8c0be58a6668264e695fd24f9e5e8f3ed6406da41ea45c672',
    'uaart_connection_monitor.py': '989acd5d3ff1ce2dc6a49810a96b4451d63d89faf558ec96da3726d369f276fd',
}
EXTERNAL_GUARDS = {
    'autopilot_inbox/cloud/seo_rehab_guard_068/seo_rehab_guard_068_repair.py':
        ('seo_rehab_guard_068_repair.py', '88922c6774bec9ea624b381f06f76167f768b2ffe57ad302f2e0fb5f3697d6f3'),
}
WRITERS = ('kadry_diagnostiki.py', 'publikaciya.py', 'publish_transaction_guard.py', 'stranica.py',
           'ua_spec84_runtime.py', 'ua_spec_permanent.py', 'yadro.py')
CORE = ('__init__.py', 'coordinator.py', 'deletion_state.py', 'retirement.py',
        'public_write_guard.py', 'runtime.py')
WRITER_RECIPE = ('build_writer_patch.py', 'cars_publication_patch.py',
                 'ua_delete_public_guard.py', 'test_writer_guard.py',
                 'test_publication_worker.py')
INSTALLER = ('package_install.py', 'lifecycle_controller.py', 'lifecycle_worker.py', 'watchdog.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def module(name, relative):
    path = HERE / relative
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


def validate_writer_receipt(raw, sources, writers, payloads):
    """A historical passing test receipt cannot authorize a changed recipe."""
    value = json.loads(raw)
    tests = value['guard_unit_tests']
    if tests.get('failed') != 0 or tests.get('skipped') != 0 or tests.get('passed', 0) <= 0:
        raise ValueError('WRITER_TEST_RECEIPT_REQUIRED')
    if value.get('recipe_sha256') != {
        name: sha((HERE / 'writer_patch' / name).read_bytes()) for name in WRITER_RECIPE
    }:
        raise ValueError('WRITER_RECIPE_RECEIPT_STALE')
    candidates = value['source_candidates']
    if set(candidates) != set(WRITERS) | {'cars_ui.py'}:
        raise ValueError('EXACT_WRITER_CANDIDATE_RECEIPT_REQUIRED')
    for name, item in candidates.items():
        baseline = (sources / name).read_bytes()
        # The writer receipt covers its own transform; the final composed bot
        # and list source receives a separate release payload hash.
        transformed = (writers.transform(name, baseline).encode()
                       if name == 'cars_ui.py' else payloads[name])
        if (item.get('status') != 'COMPILE_PASS' or
                item.get('source_sha256') != sha(baseline) or
                item.get('candidate_sha256') != sha(transformed)):
            raise ValueError('WRITER_CANDIDATE_RECEIPT_STALE:' + name)


def build(sources, output):
    sources, output = Path(sources).resolve(strict=True), Path(output).absolute()
    if output.exists() or output == sources or sources in output.parents:
        raise ValueError('FRESH_ISOLATED_OUTPUT_REQUIRED')
    for name, expected in UNCHANGED.items():
        if sha((sources / name).read_bytes()) != expected:
            raise ValueError('CURRENT_SOURCE_CHANGED:' + name)
    for destination, (name, expected) in EXTERNAL_GUARDS.items():
        if sha((sources / name).read_bytes()) != expected:
            raise ValueError('CURRENT_SOURCE_CHANGED:' + destination)
    # Only the new helper is imported here; private production modules are
    # parsed/compiled as bytes and never executed by this builder.
    sys.path.insert(0, str(HERE / 'route_patch'))
    sys.path.insert(0, str(HERE / 'writer_patch'))
    lists = module('_release_list_builder', 'list_patch/build_list_patch.py')
    bot = module('_release_bot_builder', 'bot_patch/build_bot_patch.py')
    writers = module('_release_writer_builder', 'writer_patch/build_writer_patch.py')
    routes = module('_release_route_builder', 'route_patch/build_route_patch.py')
    original_car = (sources / 'cars_ui.py').read_bytes()
    car = bot.apply_to_candidate(lists.build_candidate(original_car))
    car = writers.apply_cars_ui_to_candidate(car)
    if isinstance(car, str):
        car = car.encode()
    payloads = {'cars_ui.py': car}
    for name in WRITERS:
        payloads[name] = writers.transform(name, (sources / name).read_bytes()).encode()
    for target, source in (
        ('ua_crm_resilient_list.py', 'list_patch/ua_crm_resilient_list.py'),
        ('ua_crm_delete_bot.py', 'bot_patch/ua_crm_delete_bot.py'),
        ('ua_delete_public_guard.py', 'writer_patch/ua_delete_public_guard.py'),
        ('ua_crm_deleted_routes.py', 'route_patch/ua_crm_deleted_routes.py'),
    ):
        payloads[target] = (HERE / source).read_bytes()
    for name in CORE:
        payloads['ua_crm_deletion_core/' + name] = (HERE / 'deletion_core' / name).read_bytes()
    payloads['ua_delete_runtime.py'] = (
        b'"""Installed CRM deletion factory; no import-time mutations."""\n'
        b'from ua_crm_deletion_core.runtime import create_coordinator\n')
    wsgi = routes.transform((sources / 'www_uaart_com_ua_wsgi.py').read_bytes()).encode()
    for name, content in {**payloads, 'www_uaart_com_ua_wsgi.py': wsgi}.items():
        ast.parse(content, filename=name, feature_version=(3, 10))
        compile(content, name, 'exec')
    writer_receipt = (HERE / 'writer_patch/offline_validation.json').read_bytes()
    validate_writer_receipt(writer_receipt, sources, writers, payloads)
    public_guard = module('_release_public_guard', 'writer_patch/ua_delete_public_guard.py')
    historical = public_guard.verify_historical_evidence(
        (sources / 'emergency-plan.json').read_bytes(),
        (sources / 'public_fixture_tree/uploads/ua0002_job/console-result.json').read_bytes())
    pins = dict(UNCHANGED)
    pins.update({name: sha(value) for name, value in payloads.items() if '/' not in name})
    shared = {folder + '/' + name: kind for folder in ('site', 'video')
              for name, kind in (('index.html', 'LEGACY_HOME' if folder == 'site' else 'MODERN_HOME'),
                                  ('katalog.html', 'CATALOG'), ('sitemap.xml', 'SITEMAP'))}
    runtime_config = {
        'version': 1, 'application_schema_sha256': SCHEMA_SHA,
        'source_sha256': pins, 'shared': shared,
        'shared_routes': {name: ['https://www.uaart.com.ua/' + name] if name.startswith('video/') else []
                          for name in shared},
        'direct_route_prefixes': {'site': [], 'video': ['https://www.uaart.com.ua/video/']},
        'writers_receipt_sha256': sha(writer_receipt),
    }
    config_bytes = encoded(runtime_config)
    files = []
    # Helpers first, then writers; the active entrypoint is always last.
    ordered = sorted(payloads, key=lambda name: (2 if name == 'cars_ui.py' else
                                                1 if name in WRITERS else 0, name))
    for name in ordered:
        before = sha((sources / name).read_bytes()) if name in WRITERS or name == 'cars_ui.py' else None
        files.append({'destination': name, 'before_sha256': before,
                      'payload': 'payload/' + name, 'payload_sha256': sha(payloads[name]),
                      'role': 'entrypoint' if name == 'cars_ui.py' else 'writer' if name in WRITERS else 'helper'})
    schema_path = 'payload/ua_crm_deletion_core/deletion_state.py'
    manifest = {
        'format': 1, 'task': 'UA-ART-CRM-DELETE-RECOVERY-002-v1.0', 'root': '/home/Carix',
        'supervisor': {'id': 266084, 'command': 'python3.10 /home/Carix/start_safe.py'},
        'application_schema_sha256': SCHEMA_SHA,
        'source_guards': dict(UNCHANGED, **{name: value[1] for name, value in EXTERNAL_GUARDS.items()}),
        'files': files,
        'deletion_schema': {'payload': schema_path, 'sha256': sha(payloads['ua_crm_deletion_core/deletion_state.py'])},
        'route_patch': {'destination': '/var/www/www_uaart_com_ua_wsgi.py',
                        'before_sha256': routes.BASELINE, 'payload': 'route/www_uaart_com_ua_wsgi.py',
                        'payload_sha256': sha(wsgi), 'role': 'route'},
        'runtime_config': {'destination': 'ua_crm_deletion_state/runtime.json', 'before_sha256': None,
                           'payload': 'runtime/runtime.json', 'payload_sha256': sha(config_bytes)},
    }
    output.mkdir(mode=0o700, parents=True)
    for name, content in payloads.items():
        path = output / 'payload' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (output / 'route').mkdir()
    (output / 'route/www_uaart_com_ua_wsgi.py').write_bytes(wsgi)
    (output / 'runtime').mkdir()
    (output / 'runtime/runtime.json').write_bytes(config_bytes)
    (output / 'writers_receipt.json').write_bytes(writer_receipt)
    (output / 'manifest.json').write_bytes(encoded(manifest))
    (output / 'install').mkdir(mode=0o700)
    installer_hashes = {}
    for name in INSTALLER:
        content = (HERE / 'install' / name).read_bytes()
        ast.parse(content, filename=name, feature_version=(3, 10))
        compile(content, name, 'exec')
        (output / 'install' / name).write_bytes(content)
        installer_hashes[name] = sha(content)
    receipt = {'status': 'CANDIDATE_BUILT', 'production_ready': False, 'installed': False,
               'manifest_sha256': sha(encoded(manifest)), 'python_payloads_compiled': len(payloads) + 1,
               'runtime_config_sha256': sha(config_bytes),
               'historical_retirement_reservation': historical,
               'installation_source_sha256': installer_hashes,
               'production_blockers': ['separate installation command required by TZ 6.5',
                                       'existing unrelated AUTOPILOT_HALT remains active',
                                       'production admission and lifecycle acceptance remain required']}
    (output / 'build_receipt.json').write_bytes(encoded(receipt))
    # The independent watchdog requires private context/manifest/source files;
    # normal umask defaults must not silently make the built package unusable.
    for path in output.rglob('*'):
        path.chmod(0o700 if path.is_dir() else 0o600)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.sources, args.output), sort_keys=True))
