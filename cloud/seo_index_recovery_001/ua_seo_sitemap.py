"""One sitemap from the published catalog, never directory orphan files."""
from html.parser import HTMLParser
from pathlib import Path
import os
import re
import tempfile
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

ORIGIN = 'https://www.uaart.com.ua'
CORE = ('index.html', 'katalog.html', 'podbor.html', 'info.html')
CARD = re.compile(r'UA-[0-9]{4,}\.html', re.I)


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


def sitemap(root, catalog=None):
    root = Path(root)
    if catalog is None:
        catalog = (root/'katalog.html').read_text(encoding='utf-8')
    cards = CatalogLinks(catalog).names
    names = [name for name in CORE if (root/name).is_file()]
    names.extend(name for name in sorted(cards) if (root/name).is_file())
    body = ['<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    body.extend('  <url><loc>%s/video/%s</loc></url>' % (ORIGIN, escape(name)) for name in names)
    body.append('</urlset>')
    return ('\n'.join(body)+'\n').encode('utf-8')


def sync_after_write(path, source):
    """Refresh legacy static sitemap at the catalog publication boundary."""
    path = Path(path)
    if path.name != 'katalog.html' or path.parent.name not in ('video', 'site'):
        return
    payload = sitemap(path.parent, source)
    target = path.parent/'sitemap.xml'
    descriptor, temporary = tempfile.mkstemp(prefix='.seo-map-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
