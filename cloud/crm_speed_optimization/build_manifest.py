#!/usr/bin/env python3
'''Build a review manifest (file list plus sha256) for the CRM-SPEED-001
cloud deliverable package. This script only reads and writes files inside
its own directory (cloud/crm_speed_optimization). It never touches
production paths.
'''

import hashlib
import json
import os
import sys
import time

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_PATH = os.path.join(PACKAGE_DIR, 'MANIFEST.json')
INCLUDE_EXTENSIONS = ('.py', '.md')


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def build_manifest():
    entries = []
    for name in sorted(os.listdir(PACKAGE_DIR)):
        full = os.path.join(PACKAGE_DIR, name)
        if not os.path.isfile(full) or os.path.islink(full):
            continue
        if not name.endswith(INCLUDE_EXTENSIONS):
            continue
        st = os.stat(full)
        entries.append({'file': name, 'size': st.st_size, 'sha256': sha256_of(full)})
    return {
        'task': 'CRM-SPEED-001',
        'generated_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'production_write': 'NO',
        'files': entries,
    }


def main():
    manifest = build_manifest()
    with open(MANIFEST_PATH, 'w', encoding='utf-8') as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write('\n')
    print('Wrote manifest with ' + str(len(manifest['files'])) + ' entries to ' + MANIFEST_PATH)
    return 0


if __name__ == '__main__':
    sys.exit(main())
