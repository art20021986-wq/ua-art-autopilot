"""One sitemap from the published catalog and the search landing pages, never orphan files.

lastmod is the file's own modification date: cards change only when republished and
landing pages are rewritten only when their content changes.
"""
from html.parser import HTMLParser
from pathlib import Path
import datetime
import os
import re
import tempfile
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

ORIGIN = 'https://www.uaart.com.ua'
CORE = ('index.html', 'katalog.html', 'podbor.html', 'info.html')
CARD = re.compile(r'UA-[0-9]{4,}\.html', re.I)
LANDINGS = 'seo/*/*.html'


class CatalogLinks(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.names = set()
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = urlsplit(dict(attrs).get('href', ''))
        if href.netloc and href.netloc.lower() != 'www.uaart.com.ua':
            return
        if '/' in href.path and not href.path.startswith('/video/'):
            return
        name = href.path.rsplit('/', 1)[-1]
        if CARD.fullmatch(name):
            self.names.add(name)


def lastmod(path):
    return datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc).strftime('%Y-%m-%d')


def sitemap(root, catalog=None):
    root = Path(root)
    if catalog is None:
        catalog = (root/'katalog.html').read_text(encoding='utf-8')
    names = [name for name in CORE if (root/name).is_file()]
    names.extend(name for name in sorted(CatalogLinks(catalog).names) if (root/name).is_file())
    names.extend(path.relative_to(root).as_posix() for path in sorted(root.glob(LANDINGS)) if path.is_file())
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    body.extend('  <url><loc>%s/video/%s</loc><lastmod>%s</lastmod></url>' % (ORIGIN, escape(name), lastmod(root/name))
                for name in names)
    body.append('</urlset>')
    return ('\n'.join(body)+'\n').encode('utf-8')


def write(path, payload):
    """Atomic public file write; returns False when the content is already current."""
    path = Path(path)
    if path.is_file() and path.read_bytes() == payload:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.seo-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def sync_after_write(path, source):
    """Refresh legacy static sitemap at the catalog publication boundary."""
    path = Path(path)
    if path.name != 'katalog.html' or path.parent.name not in ('video', 'site'):
        return
    write(path.parent/'sitemap.xml', sitemap(path.parent, source))
