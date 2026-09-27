"""Install static site icons and HTML links, with a hash-bound plan and rollback."""
import argparse
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import tokenize
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/Carix/video')
BASE = ROOT.parent
NAMES = ('favicon.ico', 'favicon-96.png', 'apple-touch-icon.png')
BEGIN = '<!-- UA-ART-FAVICON-20260928 -->'
END = '<!-- /UA-ART-FAVICON-20260928 -->'
BLOCK = '\n'.join((BEGIN,
    '<link rel="icon" href="/video/brand/ua-art/favicon.ico" sizes="16x16 32x32 48x48" type="image/x-icon">',
    '<link rel="icon" href="/video/brand/ua-art/favicon-96.png" sizes="96x96" type="image/png">',
    '<link rel="apple-touch-icon" href="/video/brand/ua-art/apple-touch-icon.png" sizes="180x180">',
    END))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def icon_html(raw):
    text = raw.decode('utf-8')
    if BLOCK in text:
        if text.count(BLOCK) != 1:
            raise ValueError('DUPLICATE_ICON_BLOCK')
        return raw
    if BEGIN in text or END in text:
        raise ValueError('UNEXPECTED_ICON_BLOCK')
    heads = list(re.finditer(r'</head\s*>', text, re.I))
    if len(heads) != 1:
        raise ValueError('HEAD_NOT_UNIQUE')
    if re.search(r'<link\b[^>]*\brel\s*=\s*[\"\'][^\"\']*\b(?:icon|apple-touch-icon)\b', text, re.I):
        raise ValueError('EXISTING_ICON_REQUIRES_REVIEW')
    pos = heads[0].start()
    result = (text[:pos] + BLOCK + text[pos:]).encode('utf-8')
    if result.replace(BLOCK.encode(), b'', 1) != raw:
        raise ValueError('UNRELATED_HTML_CHANGED')
    return result


def icon_template(raw, filename):
    """Insert native metadata into the existing static HTML head literals."""
    text = raw.decode('utf-8')
    original = ast.parse(text, filename)
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    edits = []
    prefix = re.compile(r'<!doctype html><html\b[^>]*><head><meta charset=[^>]*>', re.I)
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type != tokenize.STRING:
            continue
        try:
            value = ast.literal_eval(token.string)
        except (ValueError, SyntaxError):
            continue
        if not isinstance(value, str) or not prefix.match(value) or BEGIN in value:
            continue
        quote = re.match(r"([\"'])", token.string)
        if not quote or token.string.startswith(quote[1] * 3):
            raise ValueError('UNEXPECTED_TEMPLATE_LITERAL:' + filename)
        encoded = BLOCK.replace('\\', '\\\\').replace(quote[1], '\\' + quote[1]).replace('\n', '\\n')
        marker = re.search(r'<meta charset=[^>]*>', token.string)
        if not marker:
            raise ValueError('TEMPLATE_CHARSET_NOT_FOUND:' + filename)
        pos = marker.end()
        replacement = token.string[:pos] + encoded + token.string[pos:]
        if ast.literal_eval(replacement).replace(BLOCK, '', 1) != value:
            raise ValueError('UNRELATED_TEMPLATE_CHANGED:' + filename)
        start = offsets[token.start[0] - 1] + token.start[1]
        end = offsets[token.end[0] - 1] + token.end[1]
        edits.append((start, end, replacement))
    for start, end, replacement in reversed(edits):
        text = text[:start] + replacement + text[end:]
    compile(text, filename, 'exec')
    updated = ast.parse(text, filename)
    for tree in (original, updated):
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                node.value = node.value.replace(BLOCK, '')
    if ast.dump(original) != ast.dump(updated):
        raise ValueError('UNRELATED_CODE_CHANGED:' + filename)
    if not edits and BEGIN not in text:
        raise ValueError('TEMPLATE_HEAD_NOT_FOUND:' + filename)
    return text.encode('utf-8')


def candidates():
    if ROOT.is_symlink() or not (ROOT / 'index.html').is_file():
        raise ValueError('SITE_ROOT_UNVERIFIED')
    pages = sorted(p for p in ROOT.glob('*.html') if
        p.name in {'index.html', 'katalog.html', 'podbor.html', 'info.html', 'izmeritel.html'}
        or re.fullmatch(r'UA-\d{4}(?:-[a-z0-9]+)?\.html', p.name))
    result = {}
    for name in NAMES:
        payload = (HERE / 'assets' / name).read_bytes()
        if name.endswith('.png') and payload[:8] != b'\x89PNG\r\n\x1a\n':
            raise ValueError('INVALID_PNG')
        if name.endswith('.ico') and payload[:4] != b'\x00\x00\x01\x00':
            raise ValueError('INVALID_ICO')
        target = ROOT / 'brand' / 'ua-art' / name
        if any(p.is_symlink() for p in (target, target.parent, target.parent.parent)):
            raise ValueError('ASSET_SYMLINK')
        raw = target.read_bytes() if target.exists() else None
        if raw != payload:
            result[target] = (raw, payload)
    for name in ('stranica.py', 'yadro.py', 'master_card.py'):
        path = BASE / name
        if path.is_symlink():
            raise ValueError('TEMPLATE_SYMLINK:' + name)
        raw = path.read_bytes()
        updated = icon_template(raw, name)
        if updated != raw:
            result[path] = (raw, updated)
    for path in pages:
        if path.is_symlink():
            raise ValueError('SYMLINK:' + path.name)
        raw = path.read_bytes()
        try:
            updated = icon_html(raw)
        except ValueError as exc:
            raise ValueError(path.name + ':' + str(exc)) from exc
        if updated != raw:
            result[path] = (raw, updated)
    return result, len(pages)


def description(changes):
    return {str(p.relative_to(BASE)): {'before': digest(a) if a is not None else None,
                                     'after': digest(b)} for p, (a, b) in changes.items()}


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    fd, temp = tempfile.mkstemp(prefix='.ua-icon-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    changes, page_count = candidates()
    plan = description(changes)
    plan_path = HERE / 'plan.json'
    if not args.apply:
        plan_path.write_text(json.dumps(plan, indent=2) + '\n')
        print(json.dumps({'gate_b': 'PASS', 'pages': page_count, 'changed': len(plan),
                          'plan_sha256': digest(plan_path.read_bytes())}))
        return
    if not plan_path.exists() or json.loads(plan_path.read_text()) != plan:
        raise ValueError('STALE_PLAN_RUN_PREFLIGHT_AGAIN')
    backup = HERE / ('backup-' + digest(plan_path.read_bytes())[:16] + '.zip')
    if backup.exists():
        raise ValueError('BACKUP_ALREADY_EXISTS')
    with zipfile.ZipFile(backup, 'x', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(plan))
        for path, (before, _) in changes.items():
            if before is not None:
                archive.writestr(str(path.relative_to(BASE)), before)
    with zipfile.ZipFile(backup) as archive:
        for path, (before, _) in changes.items():
            if before is not None and archive.read(str(path.relative_to(BASE))) != before:
                raise ValueError('BACKUP_VERIFICATION_FAILED')
    written = []
    try:
        for path, (before, after) in changes.items():
            live = path.read_bytes() if path.exists() else None
            if live != before:
                raise ValueError('CONCURRENT_CHANGE:' + path.name)
            atomic(path, after)
            written.append(path)
            if path.read_bytes() != after:
                raise ValueError('WRITE_VERIFICATION_FAILED')
    except Exception:
        for path in reversed(written):
            before, after = changes[path]
            if path.read_bytes() == after:
                if before is None:
                    path.unlink()
                else:
                    atomic(path, before)
        raise
    report = {'status': 'INSTALLED', 'pages': page_count, 'files_written': len(written),
              'backup': str(backup), 'backup_sha256': digest(backup.read_bytes()), 'files': plan}
    (HERE / 'receipt.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}))


if __name__ == '__main__':
    main()
