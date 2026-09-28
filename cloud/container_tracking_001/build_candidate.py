"""Upgrade routing only; preserve the installed tracking widget and renderer hooks."""
import ast
from hashlib import sha256
from pathlib import Path

SOURCE_SHA256 = {
    'ua_tracking_links.py': 'e00a626d18a47945f26278617cea567a5f3e741aae99c2ea65410bd7a07dffc5',
}
MODULES = ('ua_tracking_links.py',)
RENDERERS = ('stranica.py', 'yadro.py', 'master_card.py')
BEGIN = '    container = str(m.get("sea_container") or "").strip()\n'
AFTER = '    kind, days, target = _ua_stage_eta(m, stage)\n'
REPLACEMENT = '''    from ua_tracking_widget import render_tracking
    shipped = _ua_stage_date(m.get("sea_date_out"))
    out.append('<div class="ua-stage-v1-meta">')
    out.append(render_tracking(m.get("sea_container")))
    if shipped is not None:
        out.append('<span class="ua-stage-v1-badge">Отправлен: <b>%s</b></span>' % _ua_stage_pretty(shipped))
    out.append('</div>')

'''


def replace_metadata(source):
    nodes = [n for n in ast.parse(source).body
             if isinstance(n, ast.FunctionDef) and n.name == '_ua_delivery_stage_anchor']
    if len(nodes) != 1:
        raise ValueError('AMBIGUOUS_STAGE_RENDERER')
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    function = ''.join(lines[node.lineno-1:node.end_lineno])
    if function.count(REPLACEMENT) == 1:
        return source
    if function.count(BEGIN) != 1 or function.count(AFTER) != 1:
        raise ValueError('TRACKING_ANCHOR_CHANGED')
    start, end = function.index(BEGIN), function.index(AFTER)
    if end <= start:
        raise ValueError('TRACKING_ANCHOR_ORDER')
    function = function[:start] + REPLACEMENT + function[end:]
    result = ''.join(lines[:node.lineno-1]) + function + ''.join(lines[node.end_lineno:])
    compile(result, '<tracking-candidate>', 'exec')
    return result


def build(sources):
    if set(sources) != set(SOURCE_SHA256):
        raise ValueError('SOURCE_SET')
    result = {}
    for name, expected in SOURCE_SHA256.items():
        raw = sources[name]
        if sha256(raw).hexdigest() != expected:
            raise ValueError('SOURCE_CHANGED:' + name)
    for name in MODULES:
        result[name] = (Path(__file__).parent/name).read_bytes()
        compile(result[name], name, 'exec')
    return result
