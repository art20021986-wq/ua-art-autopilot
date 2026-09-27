"""Install the approved homepage share image with a reviewed plan and backup."""
import argparse
import ast
import fcntl
import json
from pathlib import Path
import re
import zipfile

from install import atomic, digest

HERE = Path(__file__).resolve().parent
BASE = Path('/home/Carix')
PAGE = BASE / 'video/index.html'
NAME = 'share-preview-20260928.jpg'
IMAGE_URL = 'https://www.uaart.com.ua/video/brand/ua-art/' + NAME
MARKER = '<!-- UA-ART-SHARE-20260928 -->'
BLOCK = '\n'.join((MARKER,
    '<meta property="og:url" content="https://www.uaart.com.ua/video/index.html">',
    '<meta property="og:site_name" content="UA ART COMPANY">',
    '<meta property="og:image" content="' + IMAGE_URL + '">',
    '<meta property="og:image:type" content="image/jpeg">',
    '<meta property="og:image:width" content="1200">',
    '<meta property="og:image:height" content="1200">',
    '<meta property="og:image:alt" content="UA ART — золоті літери UA та Mercedes-AMG ONE">',
    '<meta name="twitter:card" content="summary_large_image">',
    '<meta name="twitter:image" content="' + IMAGE_URL + '">',
    '<!-- /UA-ART-SHARE-20260928 -->'))


def patch_html(raw):
    source = raw.decode('utf-8')
    if BLOCK in source:
        assert source.count(BLOCK) == 1
        return raw
    assert MARKER not in source, 'UNEXPECTED_SHARE_BLOCK'
    assert not re.search(r'<meta\b[^>]*(?:og:image|og:url|twitter:image|twitter:card)', source, re.I), 'EXISTING_SHARE_METADATA'
    head = re.search(r'<head\b[^>]*>', source, re.I)
    assert head and len(re.findall(r'</head\s*>', source, re.I)) == 1, 'INVALID_HEAD'
    anchor = re.search(r'<meta\b[^>]*property=["\']og:type["\'][^>]*>', source, re.I)
    assert anchor and anchor.end() < source.lower().index('</head>'), 'OG_TYPE_MISSING'
    result = (source[:anchor.end()] + BLOCK + source[anchor.end():]).encode()
    assert result.replace(BLOCK.encode(), b'', 1) == raw
    return result


def patch_home_renderer(raw):
    source = raw.decode('utf-8')
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'sobrat_glavnuyu']
    assert len(functions) == 1, 'HOME_RENDERER_NOT_UNIQUE'
    node = functions[0]
    lines = source.splitlines(keepends=True)
    fragment = ''.join(lines[node.lineno - 1:node.end_lineno])
    if MARKER in fragment:
        return raw
    targets = [n for n in node.body if isinstance(n, ast.Expr) and
               isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Attribute) and
               isinstance(n.value.func.value, ast.Name) and n.value.func.value.id == 'c' and
               n.value.func.attr == 'append' and len(n.value.args) == 1 and
               isinstance(n.value.args[0], ast.Constant) and isinstance(n.value.args[0].value, str) and
               '<head>' in n.value.args[0].value]
    assert len(targets) == 1, 'HOME_HEAD_NOT_UNIQUE'
    anchor = targets[0]
    addition = ' ' * anchor.col_offset + 'c.append(' + repr(BLOCK) + ')\n'
    lines.insert(anchor.end_lineno, addition)
    result = ''.join(lines)
    compile(result, 'stranica.py', 'exec')
    assert result.replace(addition, '', 1) == source
    return result.encode()


def candidates():
    image = (HERE / 'assets' / NAME).read_bytes()
    assert image.startswith(b'\xff\xd8') and image.endswith(b'\xff\xd9'), 'INVALID_JPEG'
    targets = [(BASE / 'video/brand/ua-art' / NAME, image)]
    for path in (PAGE,):
        if path.exists():
            targets.append((path, patch_html(path.read_bytes())))
        elif path == PAGE:
            raise ValueError('HOME_MISSING')
    source = BASE / 'stranica.py'
    targets.append((source, patch_home_renderer(source.read_bytes())))
    changes = {}
    for path, after in targets:
        assert not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK'
        before = path.read_bytes() if path.exists() else None
        if before != after:
            changes[path] = (before, after)
    return changes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    with (BASE / '.ua_art_production_writer.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        changes = candidates()
        plan = {str(p.relative_to(BASE)): {'before': digest(a) if a is not None else None,
                                          'after': digest(b)} for p, (a, b) in changes.items()}
        plan_path = HERE / 'share-plan.json'
        if not args.apply:
            plan_path.write_text(json.dumps(plan, indent=2) + '\n')
            print(json.dumps({'gate_b': 'PASS', 'changed': len(plan), 'files': list(plan)}))
            return
        assert json.loads(plan_path.read_text()) == plan, 'STALE_PLAN'
        backup = HERE / ('share-backup-' + digest(plan_path.read_bytes())[:16] + '.zip')
        with zipfile.ZipFile(backup, 'x', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', json.dumps(plan))
            for path, (before, _) in changes.items():
                if before is not None:
                    archive.writestr(str(path.relative_to(BASE)), before)
        with zipfile.ZipFile(backup) as archive:
            for path, (before, _) in changes.items():
                if before is not None:
                    assert archive.read(str(path.relative_to(BASE))) == before
        written = []
        try:
            for path, (before, after) in changes.items():
                live = path.read_bytes() if path.exists() else None
                assert live == before, 'CONCURRENT_CHANGE:' + path.name
                atomic(path, after)
                written.append(path)
                assert path.read_bytes() == after, 'WRITE_VERIFICATION_FAILED'
        except Exception:
            for path in reversed(written):
                before, after = changes[path]
                if path.read_bytes() == after:
                    if before is None:
                        path.unlink()
                    else:
                        atomic(path, before)
            raise
        receipt = {'status': 'INSTALLED', 'files': plan, 'backup': str(backup),
                   'backup_sha256': digest(backup.read_bytes())}
        (HERE / 'share-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({'status': 'INSTALLED', 'files': list(plan), 'backup': str(backup)}))


if __name__ == '__main__':
    main()
