"""Card generators: the delivery block of a car in Kyiv (stage 4) carries no container tracking (KYIV-NO-TRACK-001).

Owner 2026-11-19: «Если автомобиль в Киеве, то отслеживать контейнер уже не нужно». The installed tracking hook
(CARRIER-TRACKING, cloud/container_tracking_001/build_candidate.py) is replaced in every generator that has it:
before Kyiv the block is exactly as now; in Kyiv the tracking widget is not rendered and the metadata row appears
only if it still has the shipping date. The hook must occur exactly once in _ua_delivery_stage_anchor.
"""
import ast

GENERATORS = ('stranica.py', 'master_card.py', 'yadro.py')
REQUIRED = ('stranica.py', 'master_card.py')
FUNCTION = '_ua_delivery_stage_anchor'
OLD = '''    from ua_tracking_widget import render_tracking
    shipped = _ua_stage_date(m.get("sea_date_out"))
    out.append('<div class="ua-stage-v1-meta">')
    out.append(render_tracking(m.get("sea_container")))
    if shipped is not None:
        out.append('<span class="ua-stage-v1-badge">Отправлен: <b>%s</b></span>' % _ua_stage_pretty(shipped))
    out.append('</div>')
'''
NEW = '''    from ua_tracking_widget import render_tracking
    shipped = _ua_stage_date(m.get("sea_date_out"))
    # KYIV-NO-TRACK-001: a car in Kyiv (stage 4) needs no container tracking.
    tracking = render_tracking(m.get("sea_container")) if stage < 4 else ""
    if tracking or shipped is not None:
        out.append('<div class="ua-stage-v1-meta">')
        out.append(tracking)
        if shipped is not None:
            out.append('<span class="ua-stage-v1-badge">Отправлен: <b>%s</b></span>' % _ua_stage_pretty(shipped))
        out.append('</div>')
'''


def has_hook(source):
    return OLD in source.decode('utf-8')


def build(name, source):
    if name not in GENERATORS:
        raise ValueError('GENERATOR_NAME:' + name)
    text = source.decode('utf-8')
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == FUNCTION]
    if len(nodes) != 1:
        raise ValueError('STAGE_RENDERER_COUNT:' + name)
    lines = text.splitlines(keepends=True)
    head, tail = ''.join(lines[:nodes[0].lineno - 1]), ''.join(lines[nodes[0].end_lineno:])
    function = ''.join(lines[nodes[0].lineno - 1:nodes[0].end_lineno])
    if function.count(OLD) != 1 or NEW in text or text.count(OLD) != 1:
        raise ValueError('TRACKING_HOOK_NOT_UNIQUE:' + name)
    result = head + function.replace(OLD, NEW) + tail
    compile(result, name, 'exec')
    return result.encode('utf-8')
