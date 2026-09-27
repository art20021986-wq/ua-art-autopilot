"""Verify and unpack the fixed delivery deployment package."""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

BASE = Path('/home/Carix/autopilot_inbox/cloud/task_068_ferry_vin')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', required=True)
    parser.add_argument('--run', required=True)
    parser.add_argument('--mode', choices=('preview', 'backup', 'install', 'verify', 'rollback'), required=True)
    parser.add_argument('--plan', default='')
    parser.add_argument('--backup', default='')
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{64}', args.bundle) or not re.fullmatch(r'[0-9]+', args.run):
        raise ValueError('IDENTITY')
    for value in (args.plan, args.backup):
        if value and not re.fullmatch(r'[0-9a-f]{64}', value):
            raise ValueError('HASH')
    archive = BASE / ('gallery-desktop-' + args.bundle + '.zip')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != args.bundle:
        raise ValueError('BUNDLE_HASH')
    package = BASE / ('gallery-desktop-' + args.bundle)
    package.mkdir(mode=0o700, exist_ok=True)
    if package.is_symlink() or package.resolve() != package:
        raise ValueError('PACKAGE_PATH')
    with zipfile.ZipFile(archive) as bundle:
        for item in bundle.infolist():
            if (not re.fullmatch(r'[a-z_]+\.(?:py|sql)', item.filename)
                    or item.file_size > 1048576):
                raise ValueError('BUNDLE_ENTRY')
            target = package / item.filename
            payload = bundle.read(item)
            if target.exists():
                if target.is_symlink() or target.read_bytes() != payload:
                    raise ValueError('PACKAGE_CHANGED')
            else:
                with target.open('xb') as handle:
                    os.chmod(target, 0o600)
                    handle.write(payload)
    result = subprocess.run([
        sys.executable, '-B', str(package / 'deployment_remote.py'),
        '--mode', args.mode, '--run', args.run, '--plan', args.plan, '--backup', args.backup,
    ], timeout=1500, check=False)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
