"""ua_seo_sitemap.sitemap (CARD-LANG-001): a card with both language versions is listed by them.

/video/ua/UA-XXXX.html and /video/ru/UA-XXXX.html replace /video/UA-XXXX.html, whose canonical points to the
Ukrainian version; a card without versions stays listed as now.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_sitemap.py'
EDITS = (
    ("    names.extend(name for name in sorted(CatalogLinks(catalog).names) if (root/name).is_file())\n",
     "    for name in sorted(CatalogLinks(catalog).names):\n"
     "        # CARD-LANG-001: a card with both language versions is listed by them.\n"
     "        versions = ['%s/%s' % (folder, name) for folder in ('ua', 'ru') if (root/folder/name).is_file()]\n"
     "        names.extend(versions if len(versions) == 2 else [name] if (root/name).is_file() else [])\n"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('SITEMAP_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
