"""Pure exact-source correction for vehicle IDs versus translation captions.

The private source stays outside Git. Installation uses the canonical candidate
builder and existing publication gates; this module performs no file writes.
"""
import ast
import hashlib
import re

SOURCE_SHA256 = '500ca67145faa38ca9f72ac6da85e2a7d1c351f8f2fcca4a2edeb34c22734c23'

SERVER_BEFORE = '''            for key in ('data-ua-card','data-ua'):
                value = (attrs.get(key) or '').strip().upper()
                if value:
                    if not re.fullmatch(r'UA-[0-9]{4,}', value):
                        raise HomeCounterError('INVALID_ID')
                    self.current['ids'].add(value)
'''
SERVER_AFTER = '''            # Explicit vehicle markers remain strict; data-ua also carries
            # language captions and contributes only a valid legacy vehicle ID.
            if 'data-ua-card' in attrs:
                value = (attrs.get('data-ua-card') or '').strip().upper()
                if not re.fullmatch(r'UA-[0-9]{4,}', value):
                    raise HomeCounterError('INVALID_ID')
                self.current['ids'].add(value)
            legacy = (attrs.get('data-ua') or '').strip().upper()
            if re.fullmatch(r'UA-[0-9]{4,}', legacy):
                self.current['ids'].add(legacy)
'''
CLIENT_BEFORE = '''        ['data-ua-card','data-ua'].forEach(key => {
          const id = (node.getAttribute(key) || '').trim().toUpperCase();
          if (id) { if (!/^UA-[0-9]{4,}$/.test(id)) throw Error('Invalid ID'); ids.add(id); }
        });'''
CLIENT_AFTER = '''        // data-ua is also a language caption; explicit vehicle markers are strict.
        if (node.hasAttribute('data-ua-card')) {
          const id = (node.getAttribute('data-ua-card') || '').trim().toUpperCase();
          if (!/^UA-[0-9]{4,}$/.test(id)) throw Error('Invalid ID');
          ids.add(id);
        }
        const legacy = (node.getAttribute('data-ua') || '').trim().toUpperCase();
        if (/^UA-[0-9]{4,}$/.test(legacy)) ids.add(legacy);'''
SELECTOR_BEFORE = "'[data-ua-card],[data-category],[data-stage],[data-etap],[data-ua-card-stage]'"
SELECTOR_AFTER = "'[data-ua-card],[data-ua],[data-category],[data-stage],[data-etap],[data-ua-card-stage]'"


def _once(source, before, after, label):
    if source.count(before) != 1:
        raise ValueError('EXACT_COUNTER_ANCHOR_REQUIRED:' + label)
    return source.replace(before, after, 1)


def patch_source(source):
    if type(source) is not str or hashlib.sha256(source.encode('utf-8')).hexdigest() != SOURCE_SHA256:
        raise ValueError('CURRENT_SITE_COUNTERS_SOURCE_SHA256_MISMATCH')
    result = _once(source, SERVER_BEFORE, SERVER_AFTER, 'server_vehicle_ids')
    assignments = [node for node in ast.parse(result).body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == 'CLIENT_SCRIPT' for target in node.targets)]
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Constant) or not isinstance(assignments[0].value.value, str):
        raise ValueError('EXACT_COUNTER_CLIENT_SCRIPT_REQUIRED')
    node = assignments[0]
    script = _once(node.value.value, CLIENT_BEFORE, CLIENT_AFTER, 'client_vehicle_ids')
    script = _once(script, SELECTOR_BEFORE, SELECTOR_AFTER, 'client_legacy_descendants')
    lines = result.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = ['CLIENT_SCRIPT = ' + repr(script) + '\n']
    result = ''.join(lines)
    compile(result, '<candidate-site-counters>', 'exec')
    return result


def _client_literal(source):
    found = [node.value.value for node in ast.parse(source).body
             if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
             and isinstance(node.value.value, str)
             and any(isinstance(target, ast.Name) and target.id == 'CLIENT_SCRIPT'
                     for target in node.targets)]
    if len(found) != 1:
        raise ValueError('EXACT_COUNTER_CLIENT_SCRIPT_REQUIRED')
    return found[0]


def patch_html_client(source_html, before_counter_source, after_counter_source):
    """Migrate one existing known inline counter script; preserve all else.

    An absent script stays absent. Unknown or duplicate identified scripts fail
    closed. Outer HTML and script-envelope whitespace are retained byte-for-byte.
    """
    if type(source_html) is not str:
        raise ValueError('COUNTER_HTML_TEXT_REQUIRED')
    expected = patch_source(before_counter_source)
    if after_counter_source != expected:
        raise ValueError('COUNTER_AFTERIMAGE_SOURCE_MISMATCH')
    before = _client_literal(before_counter_source).strip()
    after = _client_literal(after_counter_source).strip()
    scripts = []
    for match in re.finditer(r'<script\b(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>',
                             source_html, re.I | re.S):
        identified = re.search(r'''(?:^|\s)id\s*=\s*(["'])ua-site-counters-123\1(?:\s|$)''',
                               match.group('attrs'), re.I)
        if identified or '/* UA-SITE-COUNTERS-123:' in match.group('body'):
            scripts.append(match)
    if len(scripts) > 1:
        raise ValueError('DUPLICATE_COUNTER_CLIENT_SCRIPT')
    result = source_html
    status = 'ABSENT_UNCHANGED'
    if scripts:
        match = scripts[0]
        body = match.group('body')
        if body.strip() == before:
            offset = match.start('body') + len(body) - len(body.lstrip())
            result = source_html[:offset] + after + source_html[offset + len(before):]
            status = 'PATCHED_EXACT_SCRIPT'
        elif body.strip() == after:
            status = 'ALREADY_CURRENT'
        else:
            raise ValueError('UNKNOWN_COUNTER_CLIENT_SCRIPT')
    elif any(marker in source_html for marker in
             ('<!-- UA-SITE-COUNTERS-123:START -->', '<!-- UA-SITE-COUNTERS-123:END -->',
              'ua-site-counters-123', '/* UA-SITE-COUNTERS-123:')):
        raise ValueError('COUNTER_CLIENT_MARKER_WITHOUT_KNOWN_SCRIPT')
    return result, {
        'status': status,
        'before_sha256': hashlib.sha256(source_html.encode('utf-8')).hexdigest(),
        'after_sha256': hashlib.sha256(result.encode('utf-8')).hexdigest(),
        'unrelated_markup_preserved': True,
    }
