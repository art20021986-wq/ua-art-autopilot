"""Exact one-time cleanup of the already-published UA-0023 gallery."""
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


def cleanup_primary(source):
    frames = class_spans(source, 'kadr')
    if len(frames) != 38: raise ValueError('PRIMARY_FRAME_COUNT')
    changes = []
    for index, (start,end) in enumerate(frames, 1):
        frame = source[start:end]
        if 'foto/UA-0023/m/%03d.jpg' % index not in frame:
            raise ValueError('PRIMARY_PHOTO_ORDER')
        if index == 1:
            frame = ''
        else:
            frame = re.sub(r'фото '+str(index)+r'\b', 'фото '+str(index-1), frame)
            if index == 2: frame = frame.replace("loading='lazy'", "loading='eager'")
        changes.append((start,end,frame))
    result = source
    for start,end,value in reversed(changes): result = result[:start]+value+result[end:]
    match = re.search(r'var kadry=(\[[^;]+\]);', result)
    if not match: raise ValueError('PRIMARY_GALLERY_ARRAY')
    values = json.loads(match.group(1))
    if values != ['foto/UA-0023/%03d.jpg' % n for n in range(1,39)]:
        raise ValueError('PRIMARY_GALLERY_IDENTITIES')
    result = result[:match.start(1)]+json.dumps(values[1:],ensure_ascii=False)+result[match.end(1):]
    count = "<div class='schet'>38 фото"
    if result.count(count) != 1: raise ValueError('PRIMARY_DISPLAY_COUNT')
    result = result.replace(count, "<div class='schet'>37 фото")
    result = result.replace('foto/UA-0023/001.jpg', 'foto/UA-0023/002.jpg')
    if re.search(r'foto/UA-0023/(?:m/)?001\.jpg', result):
        raise ValueError('PRIMARY_TECHNICAL_REFERENCE_REMAINS')
    if len(class_spans(result, 'kadr')) != 37: raise ValueError('PRIMARY_FINAL_COUNT')
    return result


def cleanup_catalog(source):
    candidates = []
    for _,_,start,end in Spans(source).nodes:
        block = source[start:end]
        if VIN in block and 'foto/UA-0023/' in block:
            if set(re.findall(r'UA-\d{4}', block)) == {CODE}:
                candidates.append((start,end))
    if not candidates: raise ValueError('CATALOG_CARD_BOUNDARY')
    start,end = min(candidates, key=lambda pair:pair[1]-pair[0])
    block = source[start:end]
    updated = re.sub(r'(foto/UA-0023/(?:m/)?)001\.jpg', r'\g<1>002.jpg', block)
    updated, total = re.subn(r'(?<!\d)38(?= фото\b)|(?<=Фото: )38\b', '37', updated)
    if updated == block or total < 1: raise ValueError('CATALOG_PHOTO_ANCHOR')
    result = source[:start]+updated+source[end:]
    if re.search(r'foto/UA-0023/(?:m/)?001\.jpg', result):
        raise ValueError('CATALOG_TECHNICAL_REFERENCE_REMAINS')
    return result
