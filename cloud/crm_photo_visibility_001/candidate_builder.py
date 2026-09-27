"""Pin both renderers and change only their photo visibility selection."""
import ast
import hashlib
from pathlib import Path

SOURCE_SHA256 = {
    'stranica.py': '4d710266abb2a92754ff3e3fc7de86c628760bee3c455dfbb177dedec113b1a1',
    'master_card.py': 'c99b6c0271586d4f8c56e4184528ab6f20541173be9a287d9d64661b4b7184b2',
}
DEPENDENCY_SHA256 = {}
MODULES = ('photo_visibility.py',)

CHANGES = {
    'stranica.py': ('kadry_mashiny', '    # первым — первый горизонтальный кадр\n',
        '    from photo_visibility import visible_names\n'
        '    visible = set(visible_names(m, [os.path.basename(p) for p in puti]))\n'
        '    puti = [p for p in puti if os.path.basename(p) in visible]\n'
        '    # первым — первый горизонтальный кадр\n'),
    'master_card.py': ('vybrat_glavnoe',
        '    cover = os.path.basename((m.get("cover_photo") or "").strip()) if m else ""\n',
        '    from photo_visibility import visible_names\n'
        '    fajly = visible_names(m or {}, fajly)\n'
        '    if not fajly:\n'
        '        raise ValueError("No visible photo available for cover")\n'
        '    cover = os.path.basename((m.get("cover_photo") or "").strip()) if m else ""\n'),
}


def patch_function(source, name, anchor, replacement):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name]
    if len(nodes) != 1 or nodes[0].decorator_list:
        raise ValueError('FUNCTION_ANCHOR:' + name)
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    original = ''.join(lines[node.lineno-1:node.end_lineno])
    if original.count(anchor) != 1:
        raise ValueError('PHOTO_SELECTION_ANCHOR:' + name)
    result = ''.join(lines[:node.lineno-1]) + original.replace(anchor, replacement) + ''.join(lines[node.end_lineno:])
    compile(result, name, 'exec')
    return result


def build(source, dependencies=None):
    result = {}
    for name, expected in SOURCE_SHA256.items():
        raw = source[name]
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('SOURCE_DRIFT:' + name)
        result[name] = patch_function(raw.decode('utf-8'), *CHANGES[name]).encode('utf-8')
    for name in MODULES:
        result[name] = Path(__file__).with_name(name).read_bytes()
        compile(result[name], name, 'exec')
    return result
