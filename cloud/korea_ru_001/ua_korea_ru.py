"""Static Russian version /video/ru/korea.html of the Korea auctions page (KOREA-RU-001, owner «Да» 2026-11-12).

/video/korea.html is Ukrainian; every visible text and text attribute carries its Russian twin (data-ru,
data-ru-content, ...), which the site language script shows on request. Search engines index one language per
URL, so the Russian text gets its own address: the same page with the data-ru texts in place, lang="ru", its own
canonical and the hreflang pair, links made absolute for the deeper folder. The lot list, login and bid blocks are
copied as they are. Rebuilt only when korea.html changes (the source mark); never touches korea.html itself.
"""
import hashlib
import html
from pathlib import Path
import re

from ua_card_lang import ORIGIN, SKIP, TAG, absolute, attributes, set_attribute, write

SOURCE = 'korea.html'
TARGET = 'ru/korea.html'
URLS = {'uk': ORIGIN + '/video/korea.html', 'ru': ORIGIN + '/video/ru/korea.html'}
MARK = 'ua-korea-ru-source'
TEXT_ATTRIBUTES = {'title': 'title', 'aria-label': 'aria', 'placeholder': 'placeholder', 'alt': 'alt',
                   'content': 'content'}
VOID = {'meta', 'link', 'img', 'br', 'hr', 'input', 'source', 'base', 'wbr'}
# A script builds the order links from a relative address; in /video/ru/ it must name /video/.
SCRIPT_LINKS = (('"podbor.html?strana="', '"/video/podbor.html?strana="'),)


def links():
    """The hreflang pair (both pages carry the same three links)."""
    return ''.join('<link rel="alternate" hreflang="%s" href="%s">' % pair for pair in
                   (('uk', URLS['uk']), ('ru', URLS['ru']), ('x-default', URLS['uk'])))


def russian(source):
    """The page with the Russian twin of every text: an element whose only child is its text and that has
    data-ru shows data-ru; an attribute with data-ru-<name> takes that value (as the site script does)."""
    out, stack, position, last = [], [], 0, None
    for match in TAG.finditer(source):
        text = source[position:match.start()]
        whole = match.group(0)
        closing = not whole.startswith('<!--') and match.group(1)
        if text:
            parent = stack[-1] if stack else None
            only_child = last is parent and closing and parent and match.group(2).lower() == parent[0]
            if (only_child and text.strip() and parent[1].get('data-ru') is not None
                    and not any(tag in SKIP for tag, _ in stack)):
                text = html.escape(parent[1]['data-ru'], quote=False)
            out.append(text)
        position = match.end()
        last = None
        if whole.startswith('<!--'):
            out.append(whole)
            continue
        tag, raw = match.group(2).lower(), match.group(3)
        if closing:
            while stack and stack.pop()[0] != tag:
                pass
            out.append(whole)
            continue
        attrs = attributes(raw)
        if not any(t in SKIP for t, _ in stack):
            for name, suffix in TEXT_ATTRIBUTES.items():
                value = attrs.get('data-ru-' + suffix)
                if name in attrs and value is not None and value != attrs[name]:
                    raw = set_attribute(raw, name, value)
        out.append('<%s%s>' % (match.group(2), raw))
        if not raw.rstrip().endswith('/') and tag not in VOID:
            stack.append((tag, attrs))
            last = stack[-1]
    out.append(source[position:])
    return ''.join(out)


def revision(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def absolute_outside_scripts(source):
    """Relative links made absolute in the markup only: scripts build their own (already absolute) addresses."""
    parts = re.split(r'(?is)(?<=<script)(\b[^>]*>.*?)(?=</script>)', source)
    return ''.join(absolute_tag_only(part) if index % 2 else absolute(part) for index, part in enumerate(parts))


def absolute_tag_only(part):
    """A script's own tag (src) made absolute, its code kept."""
    tag, _, body = part.partition('>')
    return absolute(tag + '>') + body


def page(source):
    """The Russian page derived from korea.html."""
    result = russian(absolute_outside_scripts(source))
    for old, new in SCRIPT_LINKS:
        result = result.replace(old, new)
    result, count = re.subn(r'(<html\b[^>]*?\blang\s*=\s*)(["\'])[^"\']*\2', r'\1"ru"', result, count=1, flags=re.I)
    if count != 1:
        raise ValueError('KOREA_RU_LANG')
    result = re.sub(r'<link\s+rel=["\'](?:canonical|alternate)["\'][^>]*>', '', result, flags=re.I)
    result = re.sub(r'(<meta\s+property="og:url"\s+content=")[^"]*', r'\g<1>' + URLS['ru'], result, count=1)
    tags = '<link rel="canonical" href="%s">%s<meta name="%s" content="%s">' % (
        URLS['ru'], links(), MARK, revision(source))
    # First in <head>: the language script runs from the head and reads the hreflang pair at once.
    result, count = re.subn(r'(<head\b[^>]*>)', lambda m: m[1] + tags, result, count=1, flags=re.I)
    if count != 1:
        raise ValueError('KOREA_RU_HEAD')
    return result


def reconcile(root):
    """Writes ru/korea.html when korea.html changed; returns {'written': [...]} (empty when current)."""
    root = Path(root)
    source = (root/SOURCE).read_text(encoding='utf-8')
    target = root/TARGET
    if target.is_file() and '<meta name="%s" content="%s">' % (MARK, revision(source)) in target.read_text(encoding='utf-8'):
        return {'written': []}
    write(target, page(source).encode('utf-8'))
    return {'written': [TARGET]}
