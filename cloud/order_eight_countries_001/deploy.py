"""Explicit first installation and file rollback for the authorized order release.

Uses current-source pins and a fresh private backup. Never changes inventory,
restores a database, touches bot tokens, installs dependencies or restarts tasks.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import tempfile

import build as web_build
import integrate
import release_check
from ua_order.mysql_repository import MySQLRepository
from ua_order.runtime import load

BASE = Path('/home/Carix')
STATE = BASE/'order_requests'
MODULE = BASE/'ua_order'
MEDIA = BASE/'video/order'
LIVE = release_check.LIVE


def atomic_write(path, raw, mode):
    fd, temporary = tempfile.mkstemp(prefix='.ua-order-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(raw)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path, data):
    atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode(), 0o600)


def rollback(backup):
    backup = Path(backup).resolve()
    if backup.parent != BASE or not backup.name.startswith('order_release_check_'):
        raise ValueError('Expected the private release backup directory')
    manifest = json.loads((backup/'deployment.json').read_text())
    # Check every target before restoring any. Refuse to overwrite later edits.
    for name, live in LIVE.items():
        current = release_check.sha(live)
        if current not in (manifest['before'][name], manifest['after'][name]):
            raise ValueError('Later source change prevents rollback: '+name)
        if release_check.sha(backup/'sources'/name) != manifest['before'][name]:
            raise ValueError('Backup hash mismatch: '+name)
    if (STATE/'settings.json').is_file():
        settings = json.loads((STATE/'settings.json').read_text())
        settings['enabled'] = False
        write_json(STATE/'settings.json', settings)
    for name, live in LIVE.items():
        atomic_write(live, (backup/'sources'/name).read_bytes(), manifest['modes'][name])
    manifest['status'] = 'ROLLED_BACK_FILES_RELOAD_REQUIRED'
    write_json(backup/'deployment.json', manifest)
    # Preserve the database, session key and installed resources. No enquiry is
    # discarded, and an active process can finish before its explicit reload.
    return {'status': manifest['status'], 'backup': str(backup)}


def install(backup):
    backup = Path(backup).resolve()
    if any(path.is_symlink() for path in LIVE.values()):
        raise ValueError('Symlinked live files require a separately audited installation')
    checked = release_check.run(backup)
    sources = backup/'sources'
    settings = json.loads((web_build.ROOT/'settings.example.json').read_text())
    strings = json.loads((web_build.ROOT/'strings.json').read_text())
    # Reuse the already prepared contact-processing wording from the form.
    # This is not represented as a separate company privacy policy.
    settings.update(enabled=True, consent_version='ua-order-contact-20260927-v1',
                    consent_text={lang: strings[lang]['consent'] for lang in ('uk','ru','ka')})
    with tempfile.TemporaryDirectory(prefix='ua-order-install-', dir='/dev/shm') as temp:
        temp = Path(temp)
        integrate.build(sources, temp/'host')
        web_build.build(temp/'web', homepage=sources/'index.html', podbor=sources/'podbor.html')
        changed = {name: (temp/'host'/name).read_bytes() for name in integrate.PINS}
        changed.update({name: (temp/'web'/name).read_bytes() for name in ('index.html','podbor.html')})
        manifest = {'status': 'PREPARED', 'before': checked['source_sha256'],
                    'after': {name: hashlib.sha256(raw).hexdigest() for name, raw in changed.items()},
                    'modes': {name: path.stat().st_mode & 0o777 for name, path in LIVE.items()},
                    'consent_source': 'existing localized strings.json consent labels',
                    'consent_version': settings['consent_version']}
        write_json(backup/'deployment.json', manifest)
        if any(release_check.sha(path) != manifest['before'][name] for name, path in LIVE.items()):
            raise ValueError('Live source drifted after backup')
        # Fresh isolated database only. Explicit schema setup; no CRM migration.
        repository = MySQLRepository(**settings['mysql'])
        repository.initialize()
        # Stage new directories next to their final destinations so rename is
        # atomic on each filesystem. All paths must still be absent.
        if any(path.exists() for path in (STATE, MODULE, MEDIA)):
            raise ValueError('Feature paths appeared during preflight')
        try:
            with tempfile.TemporaryDirectory(prefix='.ua-order-stage-', dir=BASE) as staging:
                staging = Path(staging)
                shutil.copytree(web_build.ROOT/'ua_order', staging/'ua_order',
                                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                private = staging/'order_requests'
                private.mkdir(mode=0o700)
                shutil.copy2(web_build.CONFIG, private/'country_models.json')
                shutil.copy2(web_build.ROOT/'strings.json', private/'strings.json')
                (private/'session.key').write_bytes(secrets.token_bytes(32))
                write_json(private/'settings.json', settings)
                for path in private.iterdir():
                    path.chmod(0o600)
                # Preflight exact runtime against staged assets, never a fake token.
                preview = dict(settings, media_root=str(temp/'web'/'order'),
                               catalog_path=str(private/'country_models.json'),
                               strings_path=str(private/'strings.json'))
                write_json(private/'preflight.json', preview)
                load(private/'preflight.json')
                (private/'preflight.json').unlink()
                # Public static files must be readable by the hosting web server.
                with tempfile.TemporaryDirectory(prefix='.ua-order-assets-', dir=BASE/'video') as public:
                    public = Path(public)
                    shutil.copytree(temp/'web'/'order', public/'order')
                    for path in (public/'order').rglob('*'):
                        path.chmod(0o755 if path.is_dir() else 0o644)
                    (public/'order').chmod(0o755)
                    os.replace(staging/'ua_order', MODULE)
                    os.replace(private, STATE)
                    os.replace(public/'order', MEDIA)
            # Existing bot processes retain their old in-memory functions until
            # the separately requested task restart. WSGI changes after assets.
            for name in ('client_ui.py','lead_bot.py','team_bot.py','www_uaart_com_ua_wsgi.py',
                         'podbor.html','index.html'):
                atomic_write(LIVE[name], changed[name], manifest['modes'][name])
            load(STATE/'settings.json')
            if any(release_check.sha(path) != manifest['after'][name] for name, path in LIVE.items()):
                raise ValueError('Installed source verification failed')
            manifest['status'] = 'INSTALLED_RELOAD_REQUIRED'
            write_json(backup/'deployment.json', manifest)
        except BaseException:
            rollback(backup)
            raise
    return {'status': manifest['status'], 'backup': str(backup), 'countries': 8,
            'positions': 40, 'database': settings['mysql']['database'],
            'consent_text': settings['consent_text']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install','rollback'))
    parser.add_argument('--backup', required=True)
    args = parser.parse_args()
    with (BASE/'order_install.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps((install if args.action=='install' else rollback)(args.backup),
                         ensure_ascii=False, indent=2))
