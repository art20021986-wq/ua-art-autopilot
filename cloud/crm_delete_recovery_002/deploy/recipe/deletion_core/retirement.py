"""Exact source-span retirement. No rendering of another car's fields."""
from html.parser import HTMLParser
import re
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree
from xml.parsers import expat

try:
    from .public_write_guard import advertised_codes
except ImportError:
    from public_write_guard import advertised_codes


class RetirementError(RuntimeError):
    pass


def url_code(url):
    name = unquote(urlsplit(url).path).rsplit('/', 1)[-1]
    match = re.fullmatch(r'(UA-[0-9]{4})(?:-diag)?(?:-[0-9a-f]{6,10})?\.html', name, re.I)
    return match[1].upper() if match else None


def retire_html(data, code):
    """Remove single-car articles or standalone car anchors, preserving bytes.

    Unsupported or ambiguous structures refuse. Counter changes are the
    source-bound runtime adapter's responsibility after this exact transform.
    """
    source = data.decode('utf-8')
    offsets = [0]
    # HTMLParser increments line numbers only at literal LF, not every
    # separator recognized by str.splitlines() (CR/form-feed/U+2028).
    offsets.extend(match.end() for match in re.finditer('\n', source))
    nodes = []

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=False)
            self.stack = []

        def source_offset(self):
            line, col = self.getpos()
            return offsets[line - 1] + col

        def handle_starttag(self, tag, attrs):
            if tag not in ('a', 'article'):
                return
            self.stack.append((tag, self.source_offset(), dict(attrs)))

        def handle_endtag(self, tag):
            if tag not in ('a', 'article'):
                return
            if not self.stack or self.stack[-1][0] != tag:
                raise RetirementError('AMBIGUOUS_HTML_NESTING')
            _, start, attrs = self.stack.pop()
            end = source.find('>', self.source_offset())
            if end < 0:
                raise RetirementError('INCOMPLETE_HTML')
            nodes.append((tag, start, end + 1, attrs))

    parser = Parser()
    parser.feed(source)
    parser.close()
    if parser.stack:
        raise RetirementError('INCOMPLETE_HTML')
    spans = []
    for tag, start, end, attrs in nodes:
        codes = advertised_codes(source[start:end])
        target = (code in codes or url_code(attrs.get('href', '')) == code)
        if target:
            if codes - {code}:
                raise RetirementError('MULTIPLE_CARS_IN_RETIREMENT_NODE')
            spans.append((start, end))
    # Outermost recognized span subsumes its anchors.
    chosen = []
    for start, end in sorted(set(spans), key=lambda pair: (pair[0], -pair[1])):
        if chosen and start < chosen[-1][1]:
            if end > chosen[-1][1]:
                raise RetirementError('OVERLAPPING_RETIREMENT_SPANS')
            continue
        chosen.append((start, end))
    for start, end in reversed(chosen):
        source = source[:start] + source[end:]
    if code in advertised_codes(source):
        raise RetirementError('UNRECOGNIZED_TARGET_REPRESENTATION')
    return source.encode('utf-8')


def retire_sitemap(data, code):
    """Remove exact target <url> blocks without reserializing other entries."""
    source = data.decode('utf-8')
    before = ElementTree.fromstring(source)
    if before.tag.rsplit('}', 1)[-1] != 'urlset':
        raise RetirementError('URLSET_REQUIRED')
    def locations(root):
        return [element.text or '' for element in root.iter()
                if element.tag.rsplit('}', 1)[-1] == 'loc']
    expected = [url for url in locations(before) if url_code(url) != code]
    spans = []
    parser = expat.ParserCreate(namespace_separator='}')
    state = {'depth': 0, 'url': None, 'loc': None}

    def start(name, attrs):
        state['depth'] += 1
        local = name.rsplit('}', 1)[-1]
        if local == 'url':
            if state['url'] is not None or state['depth'] != 2:
                raise RetirementError('AMBIGUOUS_SITEMAP_URL_STRUCTURE')
            state['url'] = {'start': parser.CurrentByteIndex, 'locations': []}
        if local == 'loc' and state['url'] is not None:
            if state['loc'] is not None or state['depth'] != 3:
                raise RetirementError('AMBIGUOUS_SITEMAP_LOCATION')
            state['loc'] = []

    def characters(value):
        if state['loc'] is not None:
            state['loc'].append(value)

    def end(name):
        local = name.rsplit('}', 1)[-1]
        if local == 'loc' and state['loc'] is not None:
            state['url']['locations'].append(''.join(state['loc']))
            state['loc'] = None
        if local == 'url':
            entry = state['url']
            if any(url_code(loc) == code for loc in entry['locations']):
                if len(entry['locations']) != 1:
                    raise RetirementError('AMBIGUOUS_SITEMAP_ENTRY')
                end_offset = data.find(b'>', parser.CurrentByteIndex)
                if end_offset < 0:
                    raise RetirementError('INCOMPLETE_SITEMAP_ENTRY')
                spans.append((entry['start'], end_offset + 1))
            state['url'] = None
        state['depth'] -= 1

    parser.StartElementHandler = start
    parser.CharacterDataHandler = characters
    parser.EndElementHandler = end
    parser.Parse(data, True)
    for start, end in reversed(spans):
        data = data[:start] + data[end:]
    source = data.decode('utf-8')
    if locations(ElementTree.fromstring(source)) != expected:
        raise RetirementError('SITEMAP_RETIREMENT_NOT_EXACT')
    return data
