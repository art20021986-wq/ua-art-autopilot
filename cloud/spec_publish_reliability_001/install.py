"""Install only spec modules with audited baselines, writer locks and backups."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time

ROOT = Path('/home/Carix')
SOURCE = Path(__file__).resolve().parent
BASELINES = {
    'spec84_collector.py': '067602e03c8ccbd284426ceef5acf4d915481630636e0f98f6de672fd2aa006a',
    'spec_retry84.py': '658ee7d028b65a4d59162874cafbc2c01972138663c52a861178078971d1fb51',
    'ua_spec84_runtime.py': '938b8dd68f6eafa8b3022ef1dd1f03aa44fd27ec9979bef0819c36941fe022be',
    'source_policy.py': '727e871091c2a1858489ccab70085c801c2439aa623d23312bc40d7c1280ef38',
    'profile_library.py': '1211250019cf16c74f28d96539606803db92fe9a204eddfbb2a7339d174085db',
}
NAMES = ('spec_model_profiles.py', 'spec_catalog_pages.py', 'spec84_collector.py',
         'spec_retry84.py', 'ua_spec84_runtime.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check():
    for name, expected in BASELINES.items():
        path = ROOT / name
        if path.is_symlink() or digest(path.read_bytes()) != expected:
            raise RuntimeError('BASELINE_CHANGED: ' + name)
    for name in NAMES:
        compile((SOURCE / name).read_bytes(), name, 'exec')
        if name not in BASELINES and (ROOT / name).exists():
            raise RuntimeError('NEW_MODULE_ALREADY_EXISTS: ' + name)


def replace(path, data, mode=0o644):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.spec-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    check()
    print(json.dumps({'preflight': 'PASS', 'modules': list(NAMES)}), flush=True)
    if not args.apply:
        return
    # Existing application guard coordinates with publish, CRM and spec writers.
    sys.path.insert(0, str(ROOT))
    import ua_spec84_runtime as runtime
    with runtime._writer_guard('UA-0001'):
        check()
        backup = ROOT / ('spec_reliability_backup_' + time.strftime('%Y%m%d_%H%M%S', time.gmtime()))
        backup.mkdir(mode=0o700)
        previous = {}
        for name in NAMES:
            path = ROOT / name
            previous[name] = path.read_bytes() if path.exists() else None
            if path.exists():
                shutil.copy2(path, backup / name)
        databases = (runtime._legacy().SPEC_DB, runtime.QUEUE_DB)
        for path in databases:
            if path.parent != ROOT or not path.is_file():
                raise RuntimeError('UNEXPECTED_SPEC_DATABASE')
            with sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True) as db:
                with sqlite3.connect(backup / path.name) as copy:
                    db.backup(copy)
            os.chmod(backup / path.name, 0o600)
        installed = []
        try:
            for name in NAMES:
                path = ROOT / name
                if (path.read_bytes() if path.exists() else None) != previous[name]:
                    raise RuntimeError('CONCURRENT_SOURCE_CHANGE: ' + name)
                replace(path, (SOURCE / name).read_bytes(), path.stat().st_mode & 0o777 if path.exists() else 0o644)
                installed.append(name)
            after = {name: digest((ROOT / name).read_bytes()) for name in NAMES}
            if any(after[name] != digest((SOURCE / name).read_bytes()) for name in NAMES):
                raise RuntimeError('READBACK_MISMATCH')
            receipt = {'status': 'INSTALLED_RESTART_REQUIRED', 'backup': str(backup), 'sha256': after}
            (backup / 'receipt.json').write_text(json.dumps(receipt, indent=2))
            print(json.dumps(receipt), flush=True)
        except BaseException:
            for name in reversed(installed):
                path = ROOT / name
                if path.read_bytes() == (SOURCE / name).read_bytes():
                    if previous[name] is None:
                        path.unlink()
                    else:
                        replace(path, previous[name], (backup / name).stat().st_mode & 0o777)
            raise


if __name__ == '__main__':
    main()
