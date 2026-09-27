"""Read live inputs, save a private backup, rehearse file changes in memory.

This command never installs into live paths, reloads a service or sends messages.
Do not publish its private output directory or CRM snapshot.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

import build as web_build
import integrate

LIVE = {
    'lead_bot.py': Path('/home/Carix/lead_bot.py'),
    'client_ui.py': Path('/home/Carix/client_ui.py'),
    'team_bot.py': Path('/home/Carix/team_bot.py'),
    'www_uaart_com_ua_wsgi.py': Path('/var/www/www_uaart_com_ua_wsgi.py'),
    'index.html': Path('/home/Carix/video/index.html'),
    'podbor.html': Path('/home/Carix/video/podbor.html'),
}
CRM = Path('/home/Carix/crm.db')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(destination):
    started = time.monotonic()
    def progress(status, remaining, total):
        if time.monotonic() - started > 30:
            raise TimeoutError('CRM snapshot exceeded the bounded read window')
    with closing(sqlite3.connect(CRM.as_uri() + '?mode=ro', uri=True, timeout=3)) as source:
        with closing(sqlite3.connect(destination)) as backup:
            source.backup(backup, pages=256, progress=progress, sleep=0.01)
    with closing(sqlite3.connect(destination.as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('CRM backup failed integrity validation')
        tables = {}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
            # Names come from the schema, not input. Quote SQLite identifiers.
            quoted = '"' + name.replace('"', '""') + '"'
            hashes = []
            for row in db.execute('SELECT * FROM ' + quoted):
                raw = json.dumps(row, ensure_ascii=False, separators=(',', ':'),
                                 default=lambda value: {'bytes_hex': value.hex()}).encode()
                hashes.append(hashlib.sha256(raw).hexdigest())
            tables[name] = {'rows': len(hashes), 'rows_sha256': hashlib.sha256(
                '\n'.join(sorted(hashes)).encode()).hexdigest()}
    return tables


def run(output):
    output = Path(output).resolve()
    if output.exists() or not output.name.startswith('order_release_check_'):
        raise ValueError('Use a fresh private order_release_check_ directory')
    os.umask(0o077)
    # Check all source pins before making any backup or output.
    originals = {name: path.read_bytes() for name, path in LIVE.items()}
    for name in integrate.PINS:
        integrate.patch(name, originals[name])
    output.mkdir(mode=0o700)
    sources = output / 'sources'
    sources.mkdir(mode=0o700)
    for name, raw in originals.items():
        (sources / name).write_bytes(raw)
    manifest = {
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'production_runtime_modified': False, 'real_messages_sent': False,
        'source_sha256': {name: sha(sources/name) for name in originals},
        'private_output': str(output),
        'existing_feature_paths': {str(path): path.exists() for path in (
            Path('/home/Carix/ua_order'), Path('/home/Carix/order_requests'),
            Path('/home/Carix/video/order'))},
    }
    backup = output / 'crm.snapshot.db'
    manifest['crm_tables'] = snapshot(backup)
    manifest['crm_snapshot_sha256'] = sha(backup)
    manifest['crm_integrity'] = 'ok'
    # Both builders expressly refuse live destinations; keep rehearsals in
    # a local memory filesystem. Nothing under /home/Carix is an install target.
    with tempfile.TemporaryDirectory(prefix='ua-order-release-', dir='/dev/shm') as temp:
        temp = Path(temp)
        integrate.build(sources, temp/'host')
        web_build.build(temp/'web', homepage=sources/'index.html', podbor=sources/'podbor.html')
        stage = temp/'stage'
        shutil.copytree(sources, stage)
        for name in integrate.PINS:
            shutil.copy2(temp/'host'/name, stage/name)
        for name in ('index.html', 'podbor.html'):
            shutil.copy2(temp/'web'/name, stage/name)
        shutil.copytree(web_build.ROOT/'ua_order', stage/'ua_order')
        shutil.copytree(temp/'web'/'order', stage/'order')
        # Interrupted-install rollback rehearsal: restore only the six files
        # this feature replaces and remove only the two new staged directories.
        for name in originals:
            shutil.copy2(sources/name, stage/name)
        shutil.rmtree(stage/'ua_order')
        shutil.rmtree(stage/'order')
        if any(sha(stage/name) != manifest['source_sha256'][name] for name in originals):
            raise ValueError('File rollback did not restore exact bytes')
        if {p.name for p in stage.iterdir()} != set(originals):
            raise ValueError('Unexpected staged rollback output')
        manifest['file_install_rollback_rehearsal'] = 'PASS'
        manifest['built_web_files'] = len(list((temp/'web').rglob('*')))
    if sha(backup) != manifest['crm_snapshot_sha256']:
        raise ValueError('Rehearsal modified the CRM snapshot')
    manifest['source_drift_after_backup'] = [name for name, path in LIVE.items()
        if sha(path) != manifest['source_sha256'][name]]
    if manifest['source_drift_after_backup']:
        raise ValueError('Live source changed during backup; repeat preflight')
    manifest['status'] = 'BACKUP_AND_FILE_REHEARSAL_PASS'
    manifest['not_verified'] = ['Live installation/reload/rollback', 'Visual/mobile acceptance',
                                'Live Telegram route', 'Approved consent']
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    # Output contains only counts, hashes and paths; never database row values.
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    print(json.dumps(run(parser.parse_args().output), ensure_ascii=False, indent=2))
