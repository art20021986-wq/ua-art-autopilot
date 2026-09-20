"""Download an exact, reviewed read-only preflight package into private staging.

No live module is imported or replaced. Credentials are not requested or copied.
An inaccessible repository, existing destination, or changed hash stops staging.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request

ROOT = Path('/home/Carix/autopilot_inbox/cloud')

REPO = 'https://raw.githubusercontent.com/art20021986-wq/ua-art-autopilot/'


def package_mapping():
    """Exact public paths accepted by the hash-bound staging route."""
    mapping = {}
    for name in ('preflight.py', 'install_package.py', 'patch_cars_ui.py', 'patch_guard.py', 'patch_site_counters.py', 'patch_publikaciya.py',
                 'uaart_price_sync_runtime.py', 'uaart_price_sync_binding.py', 'uaart_price_sync_confirmation.py',
                 'uaart_price_control_reader.py'):
        mapping[name] = 'cloud/task088_price_sync/' + name
    mapping['uaart_price_sync_outbox.py'] = 'cloud/task088_price_sync/outbox.py'
    for name in ('uaart_market_prices.py', 'patch_yadro.py', 'patch_stranica.py',
                 'patch_catalog_design_guard.py', 'patch_stage_catalog_sync.py', 'initial_html_prices.py'):
        mapping[name] = 'cloud/task088_stage3_renderer/' + name
    for name in ('owner_policy.py', 'price_publication.py'):
        mapping[name] = 'cloud/task088_autopilot_owner_policy/' + name
    for name in ('integrate_private_sources.py', 'publication_fence.py', 'mutation_recovery.py', 'visibility_lifecycle.py'):
        mapping[name] = 'cloud/task088_v5_writer_fence/' + name
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('commit')
    parser.add_argument('bundle_sha256')
    parser.add_argument('--staging-id', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.commit) or not re.fullmatch(r'[0-9a-f]{64}', args.bundle_sha256):
        raise ValueError('EXACT_REVIEWED_COMMIT_AND_BUNDLE_REQUIRED')
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,90}', args.staging_id):
        raise ValueError('FRESH_STAGING_ID_REQUIRED')
    DEST = ROOT / ('task088_price_sync_' + args.staging_id)
    for parent in (ROOT, *ROOT.parents):
        if parent.is_symlink():
            raise ValueError('SYMLINK_PARENT_FORBIDDEN')
    if not ROOT.is_dir() or DEST.exists() or DEST.is_symlink():
        raise ValueError('EXISTING_PARENT_AND_UNUSED_DESTINATION_REQUIRED')
    def read(path):
        with urllib.request.urlopen(REPO + args.commit + '/' + path, timeout=30) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError('RESPONSE_TOO_LARGE')
        return data
    raw = read('cloud/task088_price_sync/preflight_bundle.json')
    if hashlib.sha256(raw).hexdigest() != args.bundle_sha256:
        raise ValueError('REVIEWED_BUNDLE_HASH_MISMATCH')
    bundle = json.loads(raw)
    if bundle['contract'] != 'TASK088-PRICE-SYNC-READONLY-PREFLIGHT-5':
        raise ValueError('WRONG_CONTRACT')
    mapping = package_mapping()
    if set(mapping) != set(bundle['package_sha256']):
        raise ValueError('EXACT_PACKAGE_PIN_SET_REQUIRED')
    payload = {'preflight_bundle.json': raw}
    for name, path in mapping.items():
        data = read(path)
        if hashlib.sha256(data).hexdigest() != bundle['package_sha256'][name]:
            raise ValueError('PACKAGE_HASH_MISMATCH:' + name)
        compile(data, name, 'exec')
        payload[name] = data
    DEST.mkdir(mode=0o700)
    for name, data in sorted(payload.items()):
        fd = os.open(DEST / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if (DEST / name).read_bytes() != data:
            raise ValueError('STAGED_READBACK_MISMATCH:' + name)
    print(json.dumps({'status': 'STAGED_READONLY_PREFLIGHT', 'commit': args.commit,
                      'bundle_sha256': args.bundle_sha256, 'files': len(payload),
                      'directory': str(DEST), 'production_changed': False}))


if __name__ == '__main__':
    main()
