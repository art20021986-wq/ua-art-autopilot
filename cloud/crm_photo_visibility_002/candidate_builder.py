"""Pin both renderers and the OCR-save callback; isolate technical sources."""
import ast
import hashlib
from pathlib import Path

SOURCE_SHA256 = {
    'stranica.py': 'fbb537834c9f5785e534cd730dac73c381165aff873ce73b08830c98a9ede4e6',
    'master_card.py': '5199f9f796b617c604fa01b8f4145cf7d869dcf95a28314dd0305926954348d9',
    'ai_filter.py': '7dfd84497c6d3823cd7df54834cb18aecdbc645544ca9709a88c6363a2d35cb6',
}
DEPENDENCY_SHA256 = {'ua_gallery.py':'65f00eb159b1f1292c61b1760c0181e9879e5662bf4cde27e4f76fb175822b26'}
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
        '    fajly = visible_names(m if m is not None else dannye(kod), fajly)\n'
        '    if not fajly:\n'
        '        raise ValueError("No visible photo available for cover")\n'
        '    cover = os.path.basename((m.get("cover_photo") or "").strip()) if m else ""\n'),
}


def patch_intake(source):
    """Keep OCR sources in inbox; explicit photo editors remain unchanged."""
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, ast.AsyncFunctionDef) and n.name == 'save']
    if len(nodes) != 1:
        raise ValueError('INTAKE_FUNCTION_ANCHOR')
    node = nodes[0]
    candidates = [n for n in ast.walk(node) if isinstance(n, ast.If)
                  and isinstance(n.test, ast.Name) and n.test.id == 'foto']
    if len(candidates) != 1 or candidates[0].orelse:
        raise ValueError('INTAKE_PHOTO_BLOCK_ANCHOR')
    block = candidates[0]
    body = ast.get_source_segment(source, block)
    if 'db.update_card_field("cars", card_id, "photos",' not in body:
        raise ValueError('INTAKE_WRITE_ANCHOR')
    lines = source.splitlines(keepends=True)
    result = ''.join(lines[:block.lineno-1]) + ''.join(lines[block.end_lineno:])
    anchor = 'foto, video = team_bot.collect_media(draft["inbox_id"])'
    if result.count(anchor) != 1:
        raise ValueError('INTAKE_MEDIA_ANCHOR')
    result = result.replace(anchor, 'video = team_bot.collect_media(draft["inbox_id"])[1]')
    result = result.replace('# переносим фото и видео из входящего сообщения',
                            '# Источник распознавания остаётся во входящих; переносим только видео.')
    compile(result, 'ai_filter.py', 'exec')
    return result


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
    for name, expected in DEPENDENCY_SHA256.items():
        if hashlib.sha256((dependencies or {})[name]).hexdigest() != expected:
            raise ValueError('DEPENDENCY_DRIFT:'+name)
    result = {}
    for name, expected in SOURCE_SHA256.items():
        raw = source[name]
        approved = (expected,) if isinstance(expected,str) else expected
        if hashlib.sha256(raw).hexdigest() not in approved:
            raise ValueError('SOURCE_DRIFT:' + name)
        source_text = raw.decode('utf-8')
        result[name] = (patch_intake(source_text) if name == 'ai_filter.py' else
                        patch_function(source_text, *CHANGES[name])).encode('utf-8')
    for name in MODULES:
        result[name] = Path(__file__).with_name(name).read_bytes()
        compile(result[name], name, 'exec')
    return result
