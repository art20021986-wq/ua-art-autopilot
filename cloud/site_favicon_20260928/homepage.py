"""Serve the published homepage at / without duplicating its generated file."""
from html.parser import HTMLParser
from pathlib import Path
import re

PAGE = Path('/home/Carix/video/index.html')
BASE = '<base href="/video/">'
HREF = re.compile(r'(\s+href\s*=\s*)([\"\'])(.*?)\2', re.I | re.S)
HOME = re.compile(r'^(?:\./|/video/)?index\.html(?=$|[?#])')


class _Document(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.offsets = [0]
        for line in source.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))
        self.heads = []
        self.bases = []
        self.edits = []
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text()
        line, column = self.getpos()
        start = self.offsets[line - 1] + column
        if tag == 'head':
            self.heads.append(start + len(raw))
        elif tag == 'base':
            self.bases.append(dict(attrs).get('href'))
        elif tag in ('a', 'area'):
            def href(match):
                value = match[3]
                if value.startswith('#'):
                    value = '/' + value
                else:
                    value = HOME.sub('/', value, count=1)
                return match[1] + match[2] + value + match[2]
            replacement = HREF.sub(href, raw)
            if replacement != raw:
                self.edits.append((start, start + len(raw), replacement))


def render(source):
    """Keep legacy relative assets working and homepage links on the short URL."""
    document = _Document(source)
    if len(document.heads) != 1 or document.bases not in ([], ['/video/']):
        raise ValueError('Unexpected homepage document structure')
    if not document.bases:
        point = document.heads[0]
        document.edits.append((point, point, BASE))
    for start, end, replacement in sorted(document.edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source.encode('utf-8')


def respond(environ, start_response):
    """Read the current publication for each request, including after CRM updates."""
    try:
        payload = render(PAGE.read_text(encoding='utf-8'))
        status = '200 OK'
    except (OSError, UnicodeError, ValueError):
        status = '503 Service Unavailable'
        payload = ('<!doctype html><html lang="uk"><meta charset="utf-8">'
                   '<title>UA ART COMPANY</title><body>'
                   '<p>Сторінка тимчасово недоступна.</p>'
                   '<a href="/video/index.html">Відкрити головну</a>'
                   '</body></html>').encode('utf-8')
    start_response(status, [
        ('Content-Type', 'text/html; charset=utf-8'),
        ('Content-Length', str(len(payload))),
        ('Cache-Control', 'no-cache'),
        ('X-Content-Type-Options', 'nosniff'),
    ])
    return [] if environ.get('REQUEST_METHOD', 'GET').upper() == 'HEAD' else [payload]
