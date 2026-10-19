"""Rewrite the derived search files after the catalog is installed.

The only writer of video/seo/{ua,ru}/ landing pages and video/sitemap.xml. Never
deletes: a model page stays (offering selection) after its cars are sold.
URLs added, removed or with a new lastmod in the sitemap are sent to IndexNow.
"""
from pathlib import Path
import re

import ua_indexnow
import ua_seo_catalog
import ua_seo_landings
import ua_seo_sitemap

ENTRY = re.compile(r'<loc>([^<]+)</loc><lastmod>([^<]+)</lastmod>')
KEPT = re.compile(r'<meta name="%s" content="([^"|]+)\|([^"]+)">' % ua_seo_landings.MODEL_META)


def kept_keys(root):
    keys = set()
    for lang in ua_seo_landings.LANGS:
        for path in sorted((root/'seo'/ua_seo_landings.DIRS[lang]).glob('*.html')):
            found = KEPT.search(path.read_text(encoding='utf-8', errors='replace'))
            if found:
                keys.add((found.group(1), found.group(2)))
    return keys


def entries(path):
    return set(ENTRY.findall(path.read_text(encoding='utf-8'))) if path.is_file() else set()


def refresh(root):
    root = Path(root)
    before = entries(root/'sitemap.xml')
    cars = ua_seo_catalog.cars((root/'katalog.html').read_text(encoding='utf-8'))
    existing = {p.relative_to(root).as_posix() for p in root.glob(ua_seo_sitemap.LANDINGS)}
    changed = [relative for relative, html in sorted(ua_seo_landings.pages(cars, kept_keys(root), existing).items())
               if ua_seo_sitemap.write(root/relative, html.encode('utf-8'))]
    sitemap_changed = ua_seo_sitemap.write(root/'sitemap.xml', ua_seo_sitemap.sitemap(root))
    urls = {loc for loc, _ in before ^ entries(root/'sitemap.xml')}
    return {'status': 'PASS', 'cars': len(cars), 'landings_changed': changed, 'sitemap_changed': sitemap_changed,
            'indexnow': ua_indexnow.submit(urls) if sitemap_changed else {'status': 'SKIP'}}
