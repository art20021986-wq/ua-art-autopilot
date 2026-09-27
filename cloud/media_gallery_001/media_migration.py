"""One-time exact HTML migration. Retain all bytes outside media blocks."""
from dataclasses import dataclass, field
from html.parser import HTMLParser
import hashlib
import json
import re

from ua_media_gallery import MARKER, assets, render


@dataclass
class Element:
    tag: str
    attrs: dict
    start: int
    end: int = 0
    children: list = field(default_factory=list)

    def descendants(self, tag):
        return [node for child in self.children
                for node in ([child] if child.tag == tag else []) + child.descendants(tag)]


class Tree(HTMLParser):
    """Offset-preserving parser used only during migration, never at request time."""
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.lines = [0]
        self.lines.extend(match.end() for match in re.finditer('\n', source))
        self.stack = []
        self.nodes = []
        self.feed(source)

    def position(self):
        line, column = self.getpos()
        return self.lines[line-1] + column

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs), self.position())
        self.nodes.append(node)
        if self.stack:
            self.stack[-1].children.append(node)
        if tag in self.VOID:
            node.end = node.start + len(self.get_starttag_text())
        else:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1].tag != tag:
            raise ValueError('MEDIA_HTML_UNBALANCED:'+tag)
        self.stack.pop().end = self.position() + len('</'+tag+'>')


def edits(source, replacements):
    result, previous = [], 0
    for start, end, value in sorted(replacements):
        if start < previous or end < start:
            raise ValueError('MEDIA_EDITS_OVERLAP')
        result.extend([source[previous:start], value])
        previous = end
    result.append(source[previous:])
    return ''.join(result)


def upgrade_card(source, legacy_script):
    if '<!--'+MARKER+'-->' in source:
        return source
    tree = Tree(source)
    rails = [node for node in tree.nodes if 'lenta' in node.attrs.get('class','').split()]
    replacements = []
    original_urls = []
    legacy_start = "<div id='lupa'><img id='bolshoe' src='' alt=''></div><div id='lupaschet'></div>"
    if legacy_start in source:
        pattern = re.escape(legacy_start)+r'<script>var kadry=(\[.*?\]);var tek=0;'+re.escape(legacy_script)+r'</script>'
        matches = list(re.finditer(pattern, source, re.S))
        if len(matches) != 1:
            raise ValueError('MEDIA_LEGACY_VIEWER_DRIFT')
        match = matches[0]
        original_urls = json.loads(match.group(1))
        replacements.append((match.start(), match.end(), assets()))
    elif '<!--ua-gallery-desktop-v1-->' in source:
        start = source.index('<!--ua-gallery-desktop-v1-->')
        end = source.index('</script>',start)+len('</script>')
        old = source[start:end]
        match = re.search(r'\}\)\((\[.*\])\);\s*</script>$', old, re.S)
        if not match:
            raise ValueError('MEDIA_DESKTOP_VIEWER_DATA')
        original_urls = json.loads(match.group(1))
        template = old[:match.start(1)] + '[]' + old[match.end(1):]
        if hashlib.sha256(template.encode()).hexdigest() != 'dab02c53132e8b6ea1a81b3e94f764fe95e3585113a7b0f120ca6d209249ed62':
            raise ValueError('MEDIA_DESKTOP_VIEWER_DRIFT')
        replacements.append((start,end,assets()))
    else:
        if any(node.descendants('img') for node in rails):
            raise ValueError('MEDIA_PHOTO_VIEWER_MISSING')
        position = source.rfind('</body>')
        if position < 0:
            raise ValueError('MEDIA_BODY_MISSING')
        replacements.append((position,position,assets()))
    kinds = set()
    for rail in rails:
        images, videos = rail.descendants('img'), rail.descendants('video')
        if bool(images) == bool(videos) or not rail.end:
            raise ValueError('MEDIA_RAIL_CONTRACT')
        kind = 'photo' if images else 'video'
        if kind in kinds:
            raise ValueError('MEDIA_DUPLICATE_RAIL')
        kinds.add(kind)
        items = []
        if images:
            if len(images) != len(original_urls):
                raise ValueError('MEDIA_PHOTO_COUNT')
            for image, original in zip(images, original_urls):
                title = re.sub(r'\s*—\s*фото\s+\d+$', '', image.attrs.get('alt',''))
                items.append({'src': original, 'preview':image.attrs['src'], 'alt':title})
        else:
            for video in videos:
                sources = video.descendants('source')
                src = video.attrs.get('src')
                if not src and len(sources) == 1:
                    src = sources[0].attrs.get('src')
                if not src or video.descendants('track') or len(sources)>1:
                    raise ValueError('MEDIA_VIDEO_CONTRACT')
                items.append({'src':src, 'preview':video.attrs.get('poster',''), 'alt':''})
        replacements.append((rail.start, rail.end, render(kind,items)))
        # The old rail hint describes a now-removed scrolling interaction.
        tail = source[rail.end:]
        hint = re.match(r"(?:</div>)?<div class=['\"]schet['\"]>[^<]*</div>", tail)
        if hint:
            keep = '</div>' if hint.group().startswith('</div>') else ''
            replacements.append((rail.end, rail.end+hint.end(),keep))
    if original_urls and 'photo' not in kinds:
        raise ValueError('MEDIA_PHOTO_RAIL_MISSING')
    return edits(source,replacements)
