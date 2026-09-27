"""Change only tracking controls in an already published delivery block."""
from html.parser import HTMLParser
import re
from ua_tracking_widget import START, END, render_tracking

STAGE_START = '<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:START -->'
STAGE_END = '<!-- UA-ART-DELIVERY-STAGES-PERMANENT-V1:END -->'
VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.source, self.stack, self.nodes = source, [], []
        self.lines = [0]
        self.lines.extend(match.end() for match in re.finditer('\n', source))
        self.feed(source)
        self.close()
        if self.stack:
            raise ValueError('UNCLOSED_DELIVERY_HTML')

    def char_offset(self):
        line, column = self.getpos()
        return self.lines[line-1] + column

    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'start': self.char_offset(),
                'content': self.char_offset() + len(self.get_starttag_text()), 'text': ''}
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_data(self, data):
        for node in self.stack:
            node['text'] += data

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1]['tag'] != tag:
            raise ValueError('UNBALANCED_DELIVERY_HTML')
        node = self.stack.pop()
        node['close'] = self.char_offset()
        node['end'] = self.source.index('>', self.char_offset()) + 1
        self.nodes.append(node)

    def with_class(self, value):
        return [node for node in self.nodes if value in node['attrs'].get('class', '').split()]


def upgrade_card(source, reference):
    if source.count(STAGE_START) != 1 or source.count(STAGE_END) != 1:
        raise ValueError('DELIVERY_BLOCK_COUNT')
    begin = source.index(STAGE_START) + len(STAGE_START)
    end = source.index(STAGE_END)
    if end < begin:
        raise ValueError('DELIVERY_BLOCK_ORDER')
    region = source[begin:end]
    widget = render_tracking(reference)
    if START in region or END in region:
        if region.count(START) != 1 or region.count(END) != 1:
            raise ValueError('TRACKING_BLOCK_COUNT')
        first, last = region.index(START), region.index(END) + len(END)
        if last < first:
            raise ValueError('TRACKING_BLOCK_ORDER')
        region = region[:first] + widget + region[last:]
    else:
        parsed = Elements(region)
        meta = parsed.with_class('ua-stage-v1-meta')
        if len(meta) > 1:
            raise ValueError('METADATA_COUNT')
        remove = parsed.with_class('ua-stage-v1-container-row')
        remove += [node for node in parsed.with_class('ua-stage-v1-badge')
                   if re.match(r'^\s*(?:Контейнер|Container|კონტეინერი)\s*:', node['text'], re.I)]
        remove += parsed.with_class('ua-stage-v1-track-link')
        ranges = []
        for node in sorted(remove, key=lambda n: (n['start'], -n['end'])):
            if ranges and node['start'] < ranges[-1][1]:
                if node['end'] > ranges[-1][1]:
                    raise ValueError('TRACKING_ELEMENT_OVERLAP')
                continue
            ranges.append((node['start'], node['end']))
        if meta:
            insertion, addition = meta[0]['content'], widget
        else:
            eta = parsed.with_class('ua-stage-v1-eta')
            if len(eta) != 1:
                raise ValueError('ETA_ANCHOR_COUNT')
            insertion = eta[0]['start']
            addition = '<div class="ua-stage-v1-meta">' + widget + '</div>'
        edits = [(start, stop, '') for start, stop in ranges]
        edits.append((insertion, insertion, addition))
        for start, stop, replacement in sorted(edits, reverse=True):
            region = region[:start] + replacement + region[stop:]
    return source[:begin] + region + source[end:]
