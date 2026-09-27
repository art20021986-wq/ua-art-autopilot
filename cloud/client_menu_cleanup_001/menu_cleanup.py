"""Remove the six owner-selected links from vitrina's main client menu.

Run with Python's -S flag: preview, install, or check. No bot/API calls.
"""
import ast
import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

SOURCE = Path('/home/Carix/vitrina.py')
STATE = Path('/home/Carix/client_menu_cleanup_20260927.json')
REMOVED = {
    '🚗 Открыть каталог', '🇰🇷 Подбор из Кореи', '🇯🇵 Подбор из Японии',
    '🇺🇸 Подбор из Америки', '🇪🇺 Подбор из Европы', '🇨🇳 Подбор из Китая',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def menu(source, ready, owner, count):
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ('ekran_start', 'knopki_stran')]
    countries = next(n.value for n in tree.body if isinstance(n, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'STRANY_PODBOR'
                             for t in n.targets))
    env = {'mashiny': lambda: [None] * count, 'katalog_gotov': lambda: ready,
           'sajt': lambda: 'https://www.uaart.com.ua/video',
           'time': SimpleNamespace(time=lambda: 123),
           'fajl': lambda name: 'owner', 'STRANY_PODBOR': ast.literal_eval(countries)}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), 'exec'), env)
    return env['ekran_start']('owner' if owner else None)


def candidate(source):
    tree = ast.parse(source)
    screen = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == 'ekran_start')
    branch = next(n for n in screen.body if isinstance(n, ast.If)
                  and isinstance(n.test, ast.Call)
                  and isinstance(n.test.func, ast.Name)
                  and n.test.func.id == 'katalog_gotov')
    assignment, = branch.body
    assert isinstance(assignment, ast.Assign)
    assert [t.id for t in assignment.targets] == ['knopki']
    old = assignment.value
    assert isinstance(old, ast.BinOp) and isinstance(old.op, ast.Add)
    assert isinstance(old.right, ast.List) and len(old.right.elts) == 1
    assert ast.get_source_segment(source, old).count('knopki_stran()') == 1
    lines = source.encode().splitlines(keepends=True)
    start = sum(map(len, lines[:old.lineno - 1])) + old.col_offset
    end = sum(map(len, lines[:old.end_lineno - 1])) + old.end_col_offset
    data = source.encode()
    result = (data[:start] + ast.get_source_segment(source, old.right).encode()
              + data[end:]).decode()
    assignment.value = copy.deepcopy(old.right)
    assert ast.dump(tree) == ast.dump(ast.parse(result)), 'Unexpected code change'
    compile(result, str(SOURCE), 'exec')
    for ready in (False, True):
        for owner in (False, True):
            for count in (0, 23):
                text, rows = menu(source, ready, owner, count)
                new_text, new_rows = menu(result, ready, owner, count)
                assert text == new_text
                if ready:
                    deleted = {' '.join(button[0].split()) for row in rows for button in row
                               if ' '.join(button[0].split()) in REMOVED}
                    assert deleted == REMOVED
                    expected = [row for row in rows
                                if not any(' '.join(button[0].split()) in REMOVED
                                           for button in row)]
                    assert new_rows == expected
                else:
                    assert new_rows == rows
    return result


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'preview'
    data = SOURCE.read_bytes()
    if mode == 'check':
        state = json.loads(STATE.read_text())
        assert sha(data) == state['after_sha256']
        assert all(' '.join(button[0].split()) not in REMOVED
                   for row in menu(data.decode(), True, True, 23)[1] for button in row)
        print('CHECK PASS: all six links absent; installed source matches preview')
        return
    assert mode in ('preview', 'install')
    after = candidate(data.decode()).encode()
    state = {'before_sha256': sha(data), 'after_sha256': sha(after),
             'backup': str(SOURCE) + '.before_client_menu_cleanup_20260927'}
    if mode == 'preview':
        STATE.write_text(json.dumps(state, indent=2) + '\n')
        print(''.join(difflib.unified_diff(data.decode().splitlines(True),
              after.decode().splitlines(True), fromfile='vitrina.py', tofile='vitrina.py')))
        print('PREVIEW PASS: 8 menu scenarios; only six selected links removed')
        print('REMAINING', menu(after.decode(), True, True, 23)[1])
        print(json.dumps(state))
        return
    assert json.loads(STATE.read_text()) == state, 'Source changed since preview'
    backup = Path(state['backup'])
    if not backup.exists():
        with backup.open('xb') as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(data)
    assert backup.read_bytes() == data
    fd, temporary = tempfile.mkstemp(prefix='.vitrina-menu-', dir=SOURCE.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), SOURCE.stat().st_mode & 0o777)
            handle.write(after)
            handle.flush()
            os.fsync(handle.fileno())
        assert SOURCE.read_bytes() == data, 'Concurrent source modification'
        os.replace(temporary, SOURCE)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    assert SOURCE.read_bytes() == after
    print('INSTALL PASS', state['after_sha256'])


if __name__ == '__main__':
    main()
