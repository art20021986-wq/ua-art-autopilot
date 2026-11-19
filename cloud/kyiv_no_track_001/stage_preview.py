"""Read-only proof for KYIV-NO-TRACK-001: render every car's delivery block with a generator's stage code before
and after the edit, and read which published card pages show tracking now.

Only the generator's own stage section is loaded and run (imports aliased _ua_stage*/_UaStage*, _UA_STAGE* constants,
_ua_stage* helpers, _ua_delivery_stage_anchor and ekran), so nothing else of the generator is imported or executed.
"""
import ast
import importlib.util
from pathlib import Path
import re
import tempfile

PREFIXES = ('_ua_stage', '_UA_STAGE', '_UaStage')
FUNCTION = '_ua_delivery_stage_anchor'
START = '<!-- UA-ART-MULTI-TRACKING-001:START -->'
END = '<!-- UA-ART-MULTI-TRACKING-001:END -->'
EMPTY_META = '<div class="ua-stage-v1-meta"></div>'
STAGE = re.compile(r'data-ua-stage-current="([1-4])"')


def _names(node):
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {alias.asname or alias.name for alias in node.names}
    if isinstance(node, ast.Try):
        return {alias.asname or alias.name for sub in ast.walk(node) if isinstance(sub, (ast.Import, ast.ImportFrom))
                for alias in sub.names}
    if isinstance(node, ast.Assign):
        return {target.id for target in node.targets if isinstance(target, ast.Name)}
    if isinstance(node, ast.FunctionDef):
        return {node.name}
    return set()


def section(source):
    """The generator's stage section, its original lines in their order."""
    lines = source.splitlines(keepends=True)
    keep = [node for node in ast.parse(source).body
            if (names := _names(node)) and all(n.startswith(PREFIXES) or n in (FUNCTION, 'ekran') for n in names)]
    return ''.join(''.join(lines[node.lineno - 1:node.end_lineno]) + '\n' for node in keep)


def renderer(source):
    """The generator's _ua_delivery_stage_anchor(m), loaded as a module made of its stage section only."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'ua_stage_section.py'
        path.write_text(section(source), encoding='utf-8')
        spec = importlib.util.spec_from_file_location('ua_stage_section', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return getattr(module, FUNCTION)


def tracking(html):
    """What the delivery block shows of the tracking: button, message or none."""
    if START not in html:
        return 'none'
    part = html[html.index(START):html.index(END)]
    return 'button' if 'class="ua-stage-v1-track-link"' in part else 'message'


def without_tracking(html):
    if html.count(START) != 1 or html.count(END) != 1:
        return html
    html = html[:html.index(START)] + html[html.index(END) + len(END):]
    return html.replace(EMPTY_META, '', 1)


def compare(before_source, after_source, rows):
    """Per car: stage, tracking before/after; problems if a non-Kyiv block changes or a Kyiv block changes beyond
    losing its tracking."""
    old, new = renderer(before_source), renderer(after_source)
    cars, problems = {}, {}
    for row in rows:
        code = str(row.get('auto_number') or row.get('id'))
        before, after = old(row), new(row)
        stage = int(STAGE.search(before).group(1))
        cars[code] = {'stage': stage, 'before': tracking(before), 'after': tracking(after)}
        expected = without_tracking(before) if stage == 4 else before
        if after != expected:
            problems[code] = 'block differs beyond the tracking'
        elif stage == 4 and START in after:
            problems[code] = 'tracking still shown in Kyiv'
    return {'cars': cars, 'problems': problems,
            'kyiv_changed': sorted(c for c, v in cars.items() if v['stage'] == 4 and v['before'] != 'none'),
            'unchanged': sum(v['stage'] < 4 for v in cars.values())}


def page_state(html):
    match = STAGE.search(html)
    return {'stage': int(match.group(1)) if match else None, 'tracking': tracking(html)}
