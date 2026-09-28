"""Replace only the homepage redirect after a hash-bound preflight and backup."""
import argparse
import ast
import fcntl
import json
from pathlib import Path
import zipfile

from install import atomic, digest
import homepage

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/Carix')
WSGI = Path('/var/www/www_uaart_com_ua_wsgi.py')
MODULE = ROOT / 'ua_homepage.py'
MARKER = '# UA-ART-SHORT-HOME-20260928'


def patch_wsgi(raw):
    source = raw.decode('utf-8')
    if MARKER in source:
        assert source.count(MARKER) == 1
        return raw
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'application']
    first = functions[0]
    condition = first.body[1]
    assert isinstance(condition, ast.If), 'ROOT_BRANCH_MISSING'
    assert "environ.get('PATH_INFO', '/') == '/'" in ast.unparse(condition.test)
    assert "method in ('GET', 'HEAD')" in ast.unparse(condition.test)
    block = ast.get_source_segment(source, condition)
    assert "'301 Moved Permanently'" in block and "('Location', location)" in block
    assert len(condition.body) == 4 and not condition.orelse, 'UNEXPECTED_ROOT_HANDLER'
    lines = source.splitlines(keepends=True)
    start, end = condition.body[0].lineno - 1, condition.body[-1].end_lineno
    indent = ' ' * condition.body[0].col_offset
    replacement = [indent + MARKER + '\n',
                   indent + 'from ua_homepage import respond\n',
                   indent + 'return respond(environ, start_response)\n']
    result = ''.join(lines[:start] + replacement + lines[end:])
    changed = ast.parse(result)
    original_branch = condition.body
    updated = [n for n in changed.body if isinstance(n, ast.FunctionDef) and n.name == 'application'][0]
    updated.body[1].body = original_branch
    assert ast.dump(changed) == ast.dump(tree), 'UNRELATED_CODE_CHANGED'
    compile(result, str(WSGI), 'exec')
    return result.encode()


def preflight():
    source = homepage.PAGE.read_text(encoding='utf-8')
    result = homepage.render(source)
    assert b'<base href="/video/">' in result
    assert b'og:image' in result and b'share-preview-20260928.jpg' in result
    assert b'http-equiv="refresh"' not in result.lower()
    assert b'href="/#main-content"' in result
    assert b'href="/"' in result
    before = WSGI.read_bytes()
    after = patch_wsgi(before)
    # Execute only the isolated base request handler: no imports of CRM or wrappers.
    tree = ast.parse(after)
    node = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'application'][0]
    import sys
    previous = sys.modules.get('ua_homepage')
    sys.modules['ua_homepage'] = homepage
    try:
        scope = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<homepage-check>', 'exec'), scope)
        for method, path, wanted in [('GET', '/', '200 OK'), ('HEAD', '/', '200 OK'),
                                     ('GET', '/missing', '404 Not Found'), ('POST', '/', '404 Not Found')]:
            response = []
            body = scope['application']({'REQUEST_METHOD': method, 'PATH_INFO': path},
                                        lambda status, headers: response.append((status, dict(headers))))
            assert response[0][0] == wanted, (method, path, response)
            assert 'Location' not in response[0][1]
            if path == '/' and method == 'GET':
                assert b''.join(body) == result
            if method == 'HEAD':
                assert not body
    finally:
        if previous is None:
            del sys.modules['ua_homepage']
        else:
            sys.modules['ua_homepage'] = previous
    module = (HERE / 'homepage.py').read_bytes()
    compile(module, str(MODULE), 'exec')
    targets = [(MODULE, module), (WSGI, after)]
    changes = {}
    for path, content in targets:
        assert not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK'
        old = path.read_bytes() if path.exists() else None
        assert path != MODULE or old in (None, content), 'EXISTING_MODULE'
        if old != content:
            changes[path] = (old, content)
    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with (ROOT / '.ua_art_production_writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        changes = preflight()
        plan = {str(path): {'before': digest(a) if a is not None else None, 'after': digest(b)}
                for path, (a, b) in changes.items()}
        plan_file = HERE / 'short-home-plan.json'
        if not args.apply:
            plan_file.write_text(json.dumps(plan, indent=2) + '\n')
            print(json.dumps({'gate_b': 'PASS', 'files': list(plan)}))
            return
        assert json.loads(plan_file.read_text()) == plan, 'STALE_PLAN'
        backup = HERE / ('short-home-backup-' + digest(plan_file.read_bytes())[:16] + '.zip')
        with zipfile.ZipFile(backup, 'x', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(plan))
            for path, (old, _) in changes.items():
                if old is not None:
                    archive.writestr(str(path).lstrip('/'), old)
        with zipfile.ZipFile(backup) as archive:
            for path, (old, _) in changes.items():
                if old is not None:
                    assert archive.read(str(path).lstrip('/')) == old
        written = []
        try:
            for path, (old, content) in changes.items():
                assert (path.read_bytes() if path.exists() else None) == old, 'CONCURRENT_CHANGE'
                atomic(path, content)
                written.append(path)
                assert path.read_bytes() == content
        except Exception:
            for path in reversed(written):
                old, content = changes[path]
                if path.read_bytes() == content:
                    if old is None:
                        path.unlink()
                    else:
                        atomic(path, old)
            raise
        (HERE / 'short-home-receipt.json').write_text(json.dumps({'files': plan, 'backup': str(backup)}, indent=2))
        print(json.dumps({'status': 'INSTALLED', 'files': list(plan), 'backup': str(backup)}))


if __name__ == '__main__':
    main()
