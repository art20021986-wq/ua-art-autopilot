"""Exact cleanup of already-published photos marked hidden in CRM."""
from html.parser import HTMLParser
import json
import re

CODE = 'UA-0023'
VIN = 'KNAG541BBNA169806'
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}


class Spans(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.lines = [0]
        for match in re.finditer('\n', source): self.lines.append(match.end())
        self.stack = []
        self.nodes = []
        self.feed(source)

    def source_offset(self):
        row, col = self.getpos()
        return self.lines[row-1]+col

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, dict(attrs), self.source_offset()))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, -1, -1):
            if self.stack[index][0] == tag:
                name, attrs, start = self.stack[index]
                del self.stack[index:]
                end = self.source.index('>', self.source_offset())+1
                self.nodes.append((name, attrs, start, end))
                break


def class_spans(source, name):
    return sorted((a,b) for _,attrs,a,b in Spans(source).nodes
                  if name in (attrs.get('class') or '').split())


def gallery_match(source):
    patterns = [r'var kadry=(\[[^;]+\]);']
    if '<!--ua-gallery-desktop-v1-->' in source:
        patterns.append(r'\}\)\((\[[^;]+\])\);\s*</script>')
    matches = [match for pattern in patterns for match in re.finditer(pattern, source)]
    if len(matches) != 1: raise ValueError('PRIMARY_GALLERY_ARRAY')
    return matches[0]


def cleanup_primary(source, code=CODE, hidden=('001.jpg',), before_count=38):
    match = gallery_match(source)
    values = json.loads(match.group(1))
    prefix = 'foto/'+code+'/'
    if (len(values) != before_count or len(set(values)) != len(values)
            or any(not re.fullmatch(re.escape(prefix)+r'[^/]+\.(?:jpg|jpeg|png|webp)', v) for v in values)):
        raise ValueError('PRIMARY_GALLERY_IDENTITIES')
    excluded = {prefix+name for name in hidden}
    if not excluded <= set(values): raise ValueError('PRIMARY_HIDDEN_IDENTITY_MISSING')
    visible = [value for value in values if value not in excluded]
    if not visible: raise ValueError('PRIMARY_NO_VISIBLE_PHOTO')
    frames = class_spans(source, 'kadr')
    if len(frames) != before_count: raise ValueError('PRIMARY_FRAME_COUNT')
    changes = []
    visible_index = 0
    for index, (start,end) in enumerate(frames, 1):
        frame = source[start:end]
        value = values[index-1]
        if prefix+'m/'+value[len(prefix):] not in frame:
            raise ValueError('PRIMARY_PHOTO_ORDER')
        if value in excluded:
            frame = ''
        else:
            visible_index += 1
            frame = re.sub(r'фото '+str(index)+r'\b', 'фото '+str(visible_index), frame)
            if visible_index == 1: frame = frame.replace("loading='lazy'", "loading='eager'")
        changes.append((start,end,frame))
    result = source
    for start,end,value in reversed(changes): result = result[:start]+value+result[end:]
    match = gallery_match(result)
    result = result[:match.start(1)]+json.dumps(visible,ensure_ascii=False)+result[match.end(1):]
    count = "<div class='schet'>%d фото" % before_count
    if result.count(count) != 1: raise ValueError('PRIMARY_DISPLAY_COUNT')
    result = result.replace(count, "<div class='schet'>%d фото" % len(visible))
    for name in hidden:
        result = re.sub('('+re.escape(prefix)+r'(?:m/)?)'+re.escape(name),
                        lambda m:m.group(1)+visible[0][len(prefix):], result)
    if len(class_spans(result, 'kadr')) != len(visible): raise ValueError('PRIMARY_FINAL_COUNT')
    return result


def cleanup_catalog(source, code=CODE, vin=VIN, hidden=('001.jpg',), before_count=38, cover='002.jpg'):
    candidates = []
    for _,_,start,end in Spans(source).nodes:
        block = source[start:end]
        if vin in block and 'foto/'+code+'/' in block:
            if set(re.findall(r'UA-\d{4}', block)) == {code}:
                candidates.append((start,end))
    if not candidates: raise ValueError('CATALOG_CARD_BOUNDARY')
    start,end = min(candidates, key=lambda pair:pair[1]-pair[0])
    block = source[start:end]
    updated = block
    for name in hidden:
        updated = re.sub('('+re.escape('foto/'+code+'/')+r'(?:m/)?)'+re.escape(name),
                         lambda m:m.group(1)+cover, updated)
    after_count = before_count-len(hidden)
    updated, total = re.subn(r'(?<!\d)'+str(before_count)+r'(?= фото\b)|(?<=Фото: )'+str(before_count)+r'\b', str(after_count), updated)
    if updated == block or total < 1: raise ValueError('CATALOG_PHOTO_ANCHOR')
    result = source[:start]+updated+source[end:]
    for name in hidden:
        if re.search(re.escape('foto/'+code+'/')+r'(?:m/)?'+re.escape(name), result):
            raise ValueError('CATALOG_TECHNICAL_REFERENCE_REMAINS')
    return result


def cleanup_page(source, path, cards):
    if path.endswith(('/katalog.html','/index.html')):
        result = source
        for code, card in sorted(cards.items()):
            if 'foto/'+code+'/' in result:
                result = cleanup_catalog(result, code, card['vin'], card['hidden'], card['before_count'], card['cover'])
        return result
    match = re.search(r'/(UA-\d{4})(?:-|\.)', path)
    if not match or match.group(1) not in cards: raise ValueError('PUBLIC_CARD_IDENTITY')
    code = match.group(1)
    card = cards[code]
    if not class_spans(source, 'kadr'):
        for name in card['hidden']:
            if re.search(re.escape('foto/'+code+'/')+r'(?:m/)?'+re.escape(name), source):
                raise ValueError('HIDDEN_REFERENCE_OUTSIDE_GALLERY')
        return source
    return cleanup_primary(source, code, card['hidden'], card['before_count'])
