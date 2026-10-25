"""Verify and unpack the fixed one-time Google Analytics setup package."""
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
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{64}', args.bundle) or not re.fullmatch(r'[0-9]+', args.run):
        raise ValueError('IDENTITY')
    archive = BASE / ('ga4setup-' + args.bundle + '.zip')
    if hashlib.sha256(archive.read_bytes()).hexdigest() != args.bundle:
        raise ValueError('BUNDLE_HASH')
    package = BASE / ('ga4setup-' + args.bundle)
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
        sys.executable, '-B', str(package / 'analytics_remote.py'), '--run', args.run,
    ], timeout=600, check=False)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
