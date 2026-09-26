"""Reviewed entrypoint for the staging-only private Preview build ZIP."""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile
import zipfile


def main():
    os.umask(0o077)
    parent = Path('/home/Carix/autopilot_inbox/cloud')
    if not parent.is_dir() or any(path.is_symlink() for path in (parent, *parent.parents)):
        raise ValueError('REGULAR_EXISTING_PRIVATE_PARENT_REQUIRED')
    archive = Path(sys.argv[0]).resolve(strict=True)
    if archive.parent != parent:
        raise ValueError('ARCHIVE_MUST_BE_IN_REVIEWED_PRIVATE_PARENT')
    stage = Path(tempfile.mkdtemp(prefix='task088-v5-preview-stage-', dir=parent))
    package = stage / 'package'
    package.mkdir(mode=0o700)
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 40 or sum(item.file_size for item in entries) > 4 * 1024 * 1024:
            raise ValueError('PACKAGE_BOUNDS_EXCEEDED')
        names = [item.filename for item in entries]
        if len(names) != len(set(names)): raise ValueError('DUPLICATE_PACKAGE_ENTRY')
        manifest = json.loads(source.read('package_manifest.json'))
        if set(names) != set(manifest['sha256']) | {'package_manifest.json'}:
            raise ValueError('PACKAGE_MANIFEST_CLOSURE_MISMATCH')
        for item in entries:
            name = item.filename
            if (name.startswith('/') or '\\' in name or '\x00' in name or str(PurePosixPath(name)) != name
                    or any(part in ('', '.', '..') for part in name.split('/')) or item.is_dir()
                    or stat.S_ISLNK(item.external_attr >> 16)):
                raise ValueError('PACKAGE_PATH_INVALID')
            raw = source.read(item)
            if name != 'package_manifest.json' and hashlib.sha256(raw).hexdigest() != manifest['sha256'][name]:
                raise ValueError('PACKAGE_HASH_MISMATCH')
            target = package / name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with open(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as output:
                output.write(raw)
    receipt = {'package_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
               'package_manifest_sha256': hashlib.sha256((package / 'package_manifest.json').read_bytes()).hexdigest(),
               'stage': str(stage)}
    with open(os.open(stage / 'PACKAGE_RECEIPT.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as output:
        json.dump(receipt, output, sort_keys=True)
    print(json.dumps(receipt, sort_keys=True), flush=True)
    return subprocess.call([sys.executable, '-I', '-B',
        str(package / 'cloud/task088_v5_acceptance/run_private_server_build.py'), str(stage)], cwd=stage)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({'stage_build': 'FAIL', 'error_type': type(error).__name__, 'production_written': False}))
        raise SystemExit(1)
