"""Produce a reviewable input draft without creating executable task authority.

Inputs are a locally built release and private source mirror. Output contains
only hashes, file identities, and public acceptance URLs, never private source
code, CRM rows, credentials, or an owner approval.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import shlex
import sys

TASK_ROOT = Path(__file__).resolve().parents[1]
REPO = TASK_ROOT.parents[1]
DEPLOY = TASK_ROOT / 'deploy'
sys.path.insert(0, str(DEPLOY))
from release_bundle import SOURCE_PATHS
from package_install import encoded as installation_encoded


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def schema_digest(value):
    return sha((json.dumps(value, sort_keys=True, separators=(',', ':'),
                           ensure_ascii=False) + '\n').encode())


def migration_draft(sources, manifest):
    release = json.loads(manifest.read_bytes())
    schema = release['deletion_schema']
    raw = (manifest.parent / schema['payload']).read_bytes()
    if sha(raw) != schema['sha256']:
        raise ValueError('PINNED_SCHEMA_PAYLOAD_CHANGED')
    tree = ast.parse(raw)
    declarations = [node for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == 'SCHEMA'
                            for target in node.targets)]
    if len(declarations) != 1:
        raise ValueError('EXACT_SCHEMA_DECLARATION_REQUIRED')
    after = ast.literal_eval(declarations[0].value)
    names = {'ua_delete_confirmations', 'ua_delete_intents', 'ua_delete_jobs'}
    if set(after) != names:
        raise ValueError('EXACT_DELETION_SCHEMA_OBJECTS_REQUIRED')
    observed = json.loads((sources / 'schema.json').read_bytes())
    before = {name: next((row[3] for row in observed
                          if row[0] == 'table' and row[1] == name), None)
              for name in sorted(names)}
    return {'path': 'production/crm.db', 'action': 'replace',
        'digest_scope': 'sqlite_schema',
        'projection_definition': 'Exact three deletion table names mapped to sqlite_master.sql or null; canonical UTF-8 sorted compact JSON plus LF',
        'expected_before_sha256': schema_digest(before),
        'expected_after_sha256': schema_digest(after),
        'before_projection': before, 'after_projection': after,
        'migration_payload_sha256': schema['sha256'],
        'database_file_hash_claimed': False,
        'crm_row_invariant': 'Logical application data digest unchanged; never restore an old database',
        'fresh_projection_verification_required': True}


def build(sources, manifest, output):
    sources, manifest = Path(sources).resolve(strict=True), Path(manifest).resolve(strict=True)
    output = Path(output).absolute()
    if 'tasks' in output.parts or 'state' in output.parts:
        raise ValueError('DRAFT_MUST_NOT_ENTER_ADMISSION_DIRECTORIES')
    source_hashes = {name: sha((sources / name).read_bytes()) for name in SOURCE_PATHS}
    observations = json.loads((TASK_ROOT / 'evidence/source_binding.json').read_bytes())
    owner_instruction = TASK_ROOT / 'evidence/OWNER_INSTALL_INSTRUCTION_20260921.json'
    if not owner_instruction.is_file():
        raise ValueError('EXISTING_OWNER_INSTRUCTION_EVIDENCE_REQUIRED')
    source_map = json.loads((DEPLOY / 'source_map.json').read_bytes())
    for item in source_map['files']:
        if sha((TASK_ROOT / item['source']).read_bytes()) != item['sha256'] or \
                sha((TASK_ROOT / item['destination']).read_bytes()) != item['sha256']:
            raise ValueError('MATERIALIZED_SOURCE_CLOSURE_STALE')
    provider = observations['provider_observation']
    always = [{'id': row['id'], 'command_sha256': sha(row['command'].encode()),
               'enabled': row['state'] == 'Running'} for row in provider['always_on']]
    scheduled = []
    for row in provider['scheduled']:
        hour, minute = (int(part) for part in row['utc'].split(':'))
        scheduled.append({'id': row['id'], 'command_sha256': sha(row['command'].encode()),
            'enabled': row['enabled'], 'hour': hour, 'minute': minute, 'interval': 'daily'})
    monitor = next(row for row in provider['always_on'] if row['id'] == 270984)
    argv = shlex.split(monitor['command'])
    argv[0] = Path(argv[0]).name
    worker = {name: sha((DEPLOY / name).read_bytes()) for name in (
        'lifecycle_controller.py', 'lifecycle_worker.py', 'package_install.py',
        'watchdog.py', 'remote_worker.py')}
    baseline = []
    installed = []
    for name in ('index.html', 'katalog.html', 'sitemap.xml'):
        raw = (sources / 'public_fixture_tree/video' / name).read_bytes()
        check = {'url': 'https://www.uaart.com.ua/video/' + name, 'status': 200,
                 'body_sha256': sha(raw)}
        baseline.append(check)
        installed.append(dict(check))
    for name in ('UA-0002.html', 'UA-0002-diag.html', 'UA-0002-a6f9d391.html'):
        url = 'https://www.uaart.com.ua/video/' + name
        baseline.append({'url': url, 'status': 302})
        installed.append({'url': url, 'status': 410})
    baseline.append({'url': 'https://www.uaart.com.ua/sitemap.xml', 'status': 200})
    installed.append({'url': 'https://www.uaart.com.ua/sitemap.xml', 'status': 200})
    checks = {'baseline': baseline, 'installed': installed}
    policy = {'version': 1, 'task_id': 'UA-ART-CRM-DELETE-RECOVERY-002-INSTALL',
        'parent_task_id': 'UA-ART-CRM-DELETE-RECOVERY-002',
        'acceptance_scope': 'INSTALLATION_AND_RUNTIME_HTTP_VERIFY',
        'package_sources': worker, 'package_manifest_path': 'package/manifest.json',
        'package_manifest_sha256': sha(manifest.read_bytes()), 'maximum_seconds': 1200,
        'provider': {'always_on': sorted(always, key=lambda x: x['id']),
                     'scheduled': sorted(scheduled, key=lambda x: x['id']),
                     'monitor_python_sha256': sha(installation_encoded(argv))},
        'http_checks': checks,
        'authority_policy': {
            'control_plane_sha256': sha((REPO / 'automation/control_plane.py').read_bytes()),
            'critical_workflow_sha256': sha((REPO / '.github/workflows/uaart_critical.yml').read_bytes()),
            'trusted_controller_sha256': sha((DEPLOY / 'controller.py').read_bytes())}}
    files = {path.relative_to(REPO).as_posix(): sha(path.read_bytes())
             for path in sorted(DEPLOY.rglob('*.py'))}
    data = {path.relative_to(REPO).as_posix(): sha(path.read_bytes())
            for path in sorted((DEPLOY / 'recipe').rglob('*'))
            if path.is_file() and path.suffix in ('.json', '.txt')}
    tests = [path for path in files if Path(path).name.startswith('test_')]
    controller_names = ('controller.py', 'backup_controller.py', 'rollback_controller.py')
    dependencies = [path for path in files if path not in tests and Path(path).name not in controller_names]
    value = {'draft_status': 'DRAFT_NOT_AUTHORIZED', 'production_allowed': False,
        'owner_approval': None, 'gate_b': 'OPEN',
        'separate_owner_installation_command': {'status': 'RECEIVED',
            'evidence_path': owner_instruction.relative_to(REPO).as_posix(),
            'evidence_sha256': sha(owner_instruction.read_bytes()),
            'requires_reconfirmation': False},
        'task_id': policy['task_id'], 'parent_task_id': policy['parent_task_id'],
        'acceptance_scope': policy['acceptance_scope'],
        'parent_acceptance_status': 'PENDING_LIVE_TELEGRAM_ACCEPTANCE',
        'package_manifest_sha256': policy['package_manifest_sha256'],
        'installation_policy_sha256': sha(installation_encoded(policy)), 'http_checks': checks,
        'sqlite_schema_migration': migration_draft(sources, manifest),
        'deployment': {'version': 1, 'source_sha256': source_hashes,
                       'data_sha256': data, 'policy': policy},
        'executable_closure': {'test_paths': tests, 'dependency_paths': dependencies,
                              'all_python_sha256': files},
        'observation_context': {'provider_observed_at': provider['observed_at'],
            'source_observation': observations['observed_at'],
            'http_body_source': 'private captured public_fixture_tree; require fresh HTTP comparison',
            'schedule_interval': 'daily template; compare complete fresh authenticated inventory',
            'native_provider_credential_present': observations.get('native_provider_credential_presence', {}).get('present'),
            'always_on_capacity_verified': False,
            'remote_process_namespace_verified': False},
        'required_before_admission': [
            'Independent assembled-package review and exact regression evidence',
            'Resolve unrelated AUTOPILOT_HALT through its existing authorized process',
            'Fresh provider inventory, available trigger capacity, and process/lock reachability',
            'Fresh public body hashes and exact baseline HTTP status read-back',
            'Exact CRITICAL manifest, Gate A and storage/health evidence for installation child',
            'Existing-schema owner approval bound by request_subject_sha256 and manifest_sha256',
            'Normal immutable launch intake; no incident-console override']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded(value))
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.sources, args.manifest, args.output)
    print(json.dumps({'draft_status': result['draft_status'], 'production_allowed': False,
                      'package_manifest_sha256': result['package_manifest_sha256']}, sort_keys=True))


if __name__ == '__main__':
    main()
