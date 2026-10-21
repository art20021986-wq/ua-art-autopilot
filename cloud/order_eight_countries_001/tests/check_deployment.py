"""Private-input installation and injected-failure rollback checks, no network."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import shutil
import tempfile
from unittest.mock import patch

import deploy


def run(sources):
    sources = Path(sources)
    results = []
    for fail in ('', 'last_file', 'module', 'state', 'media', 'manifest'):
        with tempfile.TemporaryDirectory() as root, ExitStack() as mocks:
            root = Path(root)
            (root/'video').mkdir()
            live = {name: root/name for name in deploy.LIVE}
            for name, path in live.items():
                source = sources/name
                if name in ('index.html','podbor.html') and not source.exists():
                    source = sources/name.replace('.html','-live.html')
                shutil.copy2(source, path)
            before = {name: deploy.release_check.sha(path) for name, path in live.items()}
            inventory = root/'crm.db'
            inventory.write_bytes(b'Protected inventory fixture: never restored or modified')
            backup = root/'order_release_check_test'
            def private_backup(output):
                (output/'sources').mkdir(parents=True)
                for name, path in live.items():
                    shutil.copy2(path, output/'sources'/name)
                return {'source_sha256': before}
            mocks.enter_context(patch.multiple(deploy, BASE=root, LIVE=live,
                STATE=root/'order_requests', MODULE=root/'ua_order', MEDIA=root/'video/order'))
            mocks.enter_context(patch.object(deploy.release_check, 'run', side_effect=private_backup))
            mocks.enter_context(patch.object(deploy, 'load', return_value=object()))
            db = mocks.enter_context(patch.object(deploy, 'MySQLRepository'))
            if fail:
                original, rename = deploy.atomic_write, deploy.os.replace
                tripped = [False]
                def fault_write(path, raw, mode):
                    selected = (fail == 'last_file' and path == live['index.html']) or (
                        fail == 'manifest' and path == backup/'deployment.json'
                        and json.loads(raw)['status'] == 'INSTALLED_RELOAD_REQUIRED')
                    if selected and not tripped[0]:
                        tripped[0] = True
                        raise OSError('Injected write failure')
                    return original(path, raw, mode)
                def fault_rename(source, destination):
                    target = {'module': root/'ua_order', 'state': root/'order_requests',
                              'media': root/'video/order'}.get(fail)
                    if target and destination == target and not tripped[0]:
                        tripped[0] = True
                        raise OSError('Injected publish failure')
                    return rename(source, destination)
                mocks.enter_context(patch.object(deploy, 'atomic_write', side_effect=fault_write))
                mocks.enter_context(patch.object(deploy.os, 'replace', side_effect=fault_rename))
                try:
                    deploy.install(backup)
                except OSError:
                    pass
                else:
                    raise AssertionError('Injected failure was not raised')
            else:
                result = deploy.install(backup)
                assert result['status'] == 'INSTALLED_RELOAD_REQUIRED'
                assert all(deploy.release_check.sha(path) != before[name] for name, path in live.items())
                assert json.loads((root/'order_requests/settings.json').read_text())['enabled'] is True
                deploy.rollback(backup)
            assert all(deploy.release_check.sha(path) == before[name] for name, path in live.items())
            if (root/'order_requests/settings.json').exists():
                assert json.loads((root/'order_requests/settings.json').read_text())['enabled'] is False
                assert (root/'order_requests/session.key').stat().st_mode & 0o777 == 0o600
            assert inventory.read_bytes() == b'Protected inventory fixture: never restored or modified'
            db.return_value.initialize.assert_called_once()
            results.append((fail+' failure rollback PASS') if fail else 'install and explicit rollback PASS')
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', required=True)
    print(json.dumps(run(parser.parse_args().sources)))
