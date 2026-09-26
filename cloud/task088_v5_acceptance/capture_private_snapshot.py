"""Capture task-scoped private inputs; no live source/HTML/CRM changes.

Writes one mode-0600 ZIP beneath the existing private staging parent. It must
never be committed: server Python source may contain credentials. The command
prints only archive location, hashes, counts and missing filenames.
"""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import zipfile

ROOT = Path('/home/Carix')
STAGING = ROOT / 'autopilot_inbox/cloud'
SOURCE_NAMES = (
    'team_bot.py', 'db.py', 'cars_ui.py', 'cars_schema.py', 'start_safe.py',
    'yadro.py', 'stranica.py', 'master_card.py', 'publikaciya.py',
    'catalog_design_guard.py', 'catalog_design_golden.html',
    'publish_transaction_guard.py', 'ua_stage_catalog_sync.py',
    'ua_site_counters.py', 'site_ge_inject.py',
    'uaart_bridge_wsgi.py', 'analitika_wsgi.py',
)
ASSET_NAMES = ('ua-v203.css', 'ua-site-languages.js', 'i18n.js', 'i18n-home-ge.js')


def read(name):
    path = ROOT / name
    path.resolve(strict=True).relative_to(ROOT)
    if not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError('REGULAR_BOUNDED_TASK_FILE_REQUIRED')
    return path.read_bytes()


def main():
    if not STAGING.is_dir() or any(p.is_symlink() for p in (STAGING, *STAGING.parents)):
        raise ValueError('PRIVATE_STAGING_PARENT_REQUIRED')
    conn = sqlite3.connect('file:/home/Carix/crm.db?mode=ro', uri=True, timeout=5)
    conn.execute('PRAGMA query_only=ON')
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute(
            'SELECT id,auto_number,price_uah,price_georgia,status,published FROM cars WHERE published=1 ORDER BY id')]
    finally:
        conn.close()
    import re
    if not rows or any(not re.fullmatch(r'UA-[0-9]{4}', row['auto_number']) for row in rows):
        raise ValueError('PUBLISHED_IDENTITY_INVALID')
    names = list(SOURCE_NAMES)
    for folder in ('video', 'site'):
        names.extend(folder + '/' + row['auto_number'] + '.html' for row in rows)
        names.extend(folder + '/' + name for name in ('index.html', 'katalog.html', *ASSET_NAMES))
    names.extend(('index.html', *ASSET_NAMES))
    payload, missing = {}, []
    for name in names:
        try:
            payload[name] = read(name)
        except FileNotFoundError:
            missing.append(name)
    # Exact WSGI path observed in the authenticated hosting configuration UI.
    wsgi_path = Path('/var/www/www_uaart_com_ua_wsgi.py')
    if wsgi_path.is_symlink() or not wsgi_path.is_file():
        raise ValueError('OBSERVED_WSGI_REGULAR_FILE_REQUIRED')
    payload['observed_wsgi_config.py'] = wsgi_path.read_bytes()
    payload['published_price_rows.json'] = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in payload.items()}
    payload['capture_manifest.json'] = json.dumps({'sha256': hashes, 'missing': missing,
        'published_count': len(rows), 'read_only_live': True}, sort_keys=True).encode()
    fd, archive = tempfile.mkstemp(prefix='task088-v5-private-', suffix='.zip', dir=STAGING)
    os.close(fd)
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
        for name, raw in sorted(payload.items()):
            output.writestr(name, raw)
    if any(read(name) != raw for name, raw in payload.items()
           if name not in ('published_price_rows.json', 'capture_manifest.json', 'observed_wsgi_config.py')):
        raise ValueError('LIVE_FILES_CHANGED_DURING_READ_ONLY_CAPTURE')
    if wsgi_path.read_bytes() != payload['observed_wsgi_config.py']:
        raise ValueError('WSGI_CHANGED_DURING_READ_ONLY_CAPTURE')
    print(json.dumps({'archive': archive, 'sha256': hashlib.sha256(Path(archive).read_bytes()).hexdigest(),
                      'files': len(payload), 'published_count': len(rows), 'missing': missing}))


if __name__ == '__main__':
    main()
