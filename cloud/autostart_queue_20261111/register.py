#!/usr/bin/env python3
"""Register AUTOSTART-QUEUE-20261111 (queue: max) in the runtime chain. Run from the repo root.

Usage: python3 cloud/autostart_queue_20261111/register.py "<owner words>" <reviewed main commit sha>
Order: code -> manifest -> registration -> mode, as in CRM-ROLLBACK-NONCE-20260927.
"""
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import sys

sys.path.insert(0, 'automation')
import control_plane as cp  # noqa: E402

PREFIX = cp.QUEUE_ACTIVATION_PREFIX


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def dump(path, value):
    pathlib.Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main(owner_words, source_commit):
    assert re.fullmatch(r'[0-9a-f]{40}', source_commit), 'SOURCE_COMMIT'
    assert cp.QUEUE_ACTIVATION_OWNER_COMMAND == owner_words, 'OWNER_COMMAND_NOT_IN_CODE'
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    mode_path, manifest_path = 'state/EXECUTION_MODE.json', cp.RUNTIME_MANIFEST_PATH
    shutil.copyfile(mode_path, PREFIX + '.previous-mode.json')
    shutil.copyfile(manifest_path, PREFIX + '.previous-manifest.json')
    manifest = json.loads(pathlib.Path(manifest_path).read_text())
    manifest['files'] = {name: sha(name) for name in cp.RUNTIME_PINNED_PATHS}
    manifest['generated_at'] = now.isoformat()
    dump(manifest_path, manifest)
    mode = json.loads(pathlib.Path(mode_path).read_text())
    activation = {
        'schema_version': 'UA-ART-QUEUE-REGISTRATION-1', 'task_id': 'AUTOSTART-QUEUE-20261111',
        'scope': 'CONCURRENCY_QUEUE_MAX_ONLY', 'owner_command': owner_words, 'owner_actor_id': '321059821',
        'repository': 'art20021986-wq/ua-art-autopilot', 'mode_epoch': mode['mode_epoch'],
        'halt_removed': False, 'application_write_allowed': False,
        'previous_manifest_path': PREFIX + '.previous-manifest.json',
        'previous_manifest_sha256': sha(PREFIX + '.previous-manifest.json'),
        'previous_mode_path': PREFIX + '.previous-mode.json', 'previous_mode_sha256': sha(PREFIX + '.previous-mode.json'),
        'runtime_manifest_path': manifest_path, 'runtime_manifest_sha256': sha(manifest_path),
        'changed_runtime_paths': sorted(cp.QUEUE_CHANGED_RUNTIME_PATHS),
        'registered_at': now.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source_commit': source_commit}
    dump(PREFIX + '.json', activation)
    mode.update(runtime_manifest_sha256=sha(manifest_path), runtime_activation_path=PREFIX + '.json',
                runtime_activation_sha256=sha(PREFIX + '.json'))
    dump(mode_path, mode)
    print(json.dumps(cp.verify_execution_mode(root=cp.ROOT, required_mode='AUTOMATIC'), sort_keys=True)[:300])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
