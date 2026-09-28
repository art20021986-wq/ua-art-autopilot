"""Copy the exact reviewed runtime/recipe closure into the deploy package.

This local source operation creates no authority and has no network capability.
The two source-extraction QA fixtures are copied as hash-only text evidence;
they are never imported or executed by the deployment builder.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

TASK_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ('package_install.py', 'lifecycle_controller.py', 'lifecycle_worker.py',
           'watchdog.py', 'remote_worker.py')
RECIPE_PY = (
    'build_release.py',
    'list_patch/build_list_patch.py', 'list_patch/ua_crm_resilient_list.py',
    'bot_patch/build_bot_patch.py', 'bot_patch/ua_crm_delete_bot.py',
    'writer_patch/build_writer_patch.py', 'writer_patch/cars_publication_patch.py',
    'writer_patch/ua_delete_public_guard.py',
    'route_patch/build_route_patch.py', 'route_patch/ua_crm_deleted_routes.py',
    'deletion_core/__init__.py', 'deletion_core/coordinator.py',
    'deletion_core/deletion_state.py', 'deletion_core/retirement.py',
    'deletion_core/public_write_guard.py', 'deletion_core/runtime.py',
)
RECIPE_DATA = (
    'list_patch/replacement_block.py.txt',
    'bot_patch/register_block.py.txt', 'bot_patch/replacement_handlers.py.txt',
    'writer_patch/offline_validation.json',
)
HASH_ONLY_QA = ('writer_patch/test_writer_guard.py',
                'writer_patch/test_publication_worker.py')


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_mapping():
    result = {'deploy/' + name: 'install/' + name for name in RUNTIME}
    for name in RECIPE_PY + RECIPE_DATA + tuple('install/' + n for n in RUNTIME):
        result['deploy/recipe/' + name] = name
    for name in HASH_ONLY_QA:
        result['deploy/recipe/' + name + '.txt'] = name
    return result


def materialize(root=TASK_ROOT):
    root = Path(root).resolve(strict=True)
    mapping = source_mapping()
    payloads = {}
    # Validate the entire input set before writing even one snapshot.
    for destination, source in mapping.items():
        path = root / source
        if path.is_symlink() or not path.is_file() or path.resolve() != path:
            raise ValueError('CANONICAL_REVIEWED_SOURCE_REQUIRED:' + source)
        raw = path.read_bytes()
        if destination.endswith('.py'):
            tree = ast.parse(raw, filename=destination)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                        and node.func.id in ('exec', 'eval'):
                    raise ValueError('DEPLOYMENT_AST_POLICY:' + destination)
        payloads[destination] = raw
    rows = []
    for destination, source in mapping.items():
        path = root / destination
        if path.is_symlink() or path.parent.resolve() != path.parent:
            raise ValueError('CANONICAL_SNAPSHOT_DESTINATION_REQUIRED')
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = payloads[destination]
        path.write_bytes(raw)
        if path.read_bytes() != raw:
            raise ValueError('SOURCE_SNAPSHOT_READBACK')
        rows.append({'destination': destination, 'source': source, 'sha256': _sha(raw),
                     'executed': destination.endswith('.py'),
                     'hash_only_qa': source in HASH_ONLY_QA})
    receipt = {'format': 1, 'status': 'SOURCE_CLOSURE_MATERIALIZED',
               'production_touched': False, 'authority_created': False,
               'files': rows}
    (root / 'deploy/source_map.json').write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-root', type=Path, default=TASK_ROOT)
    args = parser.parse_args()
    value = materialize(args.task_root)
    print(json.dumps({'status': value['status'], 'files': len(value['files']),
                      'production_touched': False}, sort_keys=True))


if __name__ == '__main__':
    main()
