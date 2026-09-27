"""Apply the requested static UI cleanup; no bot, database or process changes."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

from build import ROOT, one_span
from deploy import atomic_write, write_json

BASE = Path('/home/Carix')
PINS = {
    'video/podbor.html': 'f5692b08a3c6afa377acd551498380efe1e95068b0d7f64fded1331cbfed7687',
    'video/order/order.js': '56321188afaecaf98aa60cec4075e7be8b8e02120ae277074675be48d966d6bd',
    'video/order/order.css': '9badcde69ae6e304f280cceca19a06c778f9757947557a933867556e85842e96',
    'video/order/podbor.html': '107b39d14a69b298992e555e014cf0e6bc63ab717e1ef6707de0d8cad9a95c11',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def patch_page(source):
    start, end = one_span(source, lambda tag, attrs: tag == 'main' and attrs.get('id') == 'ua-order')
    fragment = source[start:end]
    a, b = one_span(fragment, lambda tag, attrs: tag == 'header' and attrs.get('class') == 'order-header')
    fragment = fragment[:a] + fragment[b:]
    opening = '<main class="ua-order" id="ua-order">'
    if fragment.count(opening) != 1:
        raise ValueError('Unexpected order form root')
    fragment = fragment.replace(opening, opening[:-1] + ' data-site-no-translate>', 1)
    result = source[:start] + fragment + source[end:]
    for name in ('order.css', 'order.js'):
        old = f'order/{name}?v=20260927.1'
        if result.count(old) != 1:
            raise ValueError('Unexpected asset include: ' + name)
        result = result.replace(old, f'order/{name}?v=20260927.2', 1)
    return result


def apply(backup):
    originals = {}
    for name, expected in PINS.items():
        path = BASE/name
        if path.is_symlink():
            raise ValueError('Unexpected symlink: ' + name)
        originals[name] = path.read_bytes()
        if sha(originals[name]) != expected:
            raise ValueError('Live source changed; review before updating: ' + name)
    changed = {f'video/order/{name}': (ROOT/'web'/name).read_bytes()
               for name in ('order.js', 'order.css', 'podbor.html')}
    # Publish the cache-busted page only after its assets are in place.
    changed['video/podbor.html'] = patch_page(originals['video/podbor.html'].decode()).encode()
    manifest = {'status': 'PREPARED', 'before': PINS,
                'after': {name: sha(raw) for name, raw in changed.items()},
                'modes': {name: (BASE/name).stat().st_mode & 0o777 for name in PINS}}
    backup.mkdir(mode=0o700)
    for name, raw in originals.items():
        path = backup/name
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(path, raw, 0o600)
    write_json(backup/'manifest.json', manifest)
    try:
        for name, raw in changed.items():
            if sha((BASE/name).read_bytes()) != PINS[name]:
                raise ValueError('Concurrent source change: ' + name)
            atomic_write(BASE/name, raw, manifest['modes'][name])
        if any(sha((BASE/name).read_bytes()) != value for name, value in manifest['after'].items()):
            raise ValueError('Installed file verification failed')
    except BaseException:
        rollback(backup)
        raise
    manifest['status'] = 'INSTALLED_STATIC_UI'
    write_json(backup/'manifest.json', manifest)
    return {'status': manifest['status'], 'backup': str(backup), 'sha256': manifest['after']}


def rollback(backup):
    manifest = json.loads((backup/'manifest.json').read_text())
    for name in PINS:
        if sha((BASE/name).read_bytes()) not in (manifest['before'][name], manifest['after'][name]):
            raise ValueError('Later edits prevent rollback: ' + name)
        if sha((backup/name).read_bytes()) != manifest['before'][name]:
            raise ValueError('Backup mismatch: ' + name)
    for name in PINS:
        atomic_write(BASE/name, (backup/name).read_bytes(), manifest['modes'][name])
    manifest['status'] = 'ROLLED_BACK_STATIC_UI'
    write_json(backup/'manifest.json', manifest)
    return {'status': manifest['status'], 'backup': str(backup)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'rollback'))
    parser.add_argument('--backup', required=True)
    args = parser.parse_args()
    backup = Path(args.backup).resolve()
    if backup.parent != BASE or not backup.name.startswith('order_ui_cleanup_'):
        raise ValueError('Use a fresh private /home/Carix/order_ui_cleanup_* backup')
    with (BASE/'order_install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps((apply if args.action == 'apply' else rollback)(backup), indent=2))
