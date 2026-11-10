"""Build the SPEED-002 candidate (owner «Да» 2026-11-08 to items 1, 2 and 3 of tasks/SPEED-002.md).

1. One address per car: the catalogue links /video/ua/UA-XXXX.html and the landing tiles and their ItemList the
   card's version in the page language (ua_card_urls.py, new); ua_seo_metadata.normalize keeps the catalogue so at
   every write; ua_seo_catalog.py still finds the cars from those links. A real 301 is not possible: PythonAnywhere
   serves /video/ as static files, outside the web app.
2. Home stage pictures: a 600 px copy and srcset for phones (ua_stage_images.py, new; run by
   site_ge_inject.inject_html for every page write); the copies for today's pictures are part of this plan.
3. Order page: the five style files of blocks that appear only after a choice or in the dialog load without
   holding back the first paint (media="print" swap, noscript fallback).
Texts, markup order, photos, CRM data and every other byte stay as they are.
"""
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
NEW_MODULES = ('ua_card_urls.py', 'ua_stage_images.py')
# Public pages only: site/ is not served (ANALYTICS2-INSTALL-20261109: /site/ 404) and its copies differ (R2, R4);
# writers that also fill site/ apply the modules there at their next write.
CATALOG_PAGES = ('video/katalog.html',)
HOME_PAGES = ('video/index.html',)
ORDER_PAGES = ('video/podbor.html',)
LATER_STYLES = ('model-note', 'model-price', 'finance-link', 'gallery', 'quick-lead')
STYLE_LINK = re.compile(r'<link rel="stylesheet" href="(order/(%s)\.css\?v=[0-9.]+)">' % '|'.join(LATER_STYLES))
EDITS = {
    'ua_seo_catalog.py': [
        ("""CODE = re.compile(r'href="(UA-[0-9]{4,})\\.html"')""",
         """CODE = re.compile(r'href="(?:ua/)?(UA-[0-9]{4,})\\.html"')  # SPEED-002: links to the ua version"""),
    ],
    'ua_seo_metadata.py': [
        ("""    name = PurePath(str(file_name)).name\n""",
         """    name = PurePath(str(file_name)).name\n    if name == 'katalog.html':  # SPEED-002: one address per car\n        from ua_card_urls import catalog_links\n        source = catalog_links(source)\n"""),
    ],
    'ua_seo_landings.py': [
        ('import ua_photo_copies as photo_copies\n', 'import ua_card_urls as card_urls\nimport ua_photo_copies as photo_copies\n'),
        ("""            escape(c['url']), image, escape(c['name']), price, escape(details)))""",
         """            escape(card_urls.preferred(c['url'], lang)), image, escape(c['name']), price, escape(details)))  # SPEED-002"""),
        ("""schema.item_list(cars), faq_ld)""", """schema.item_list(card_urls.for_lang(cars, lang)), faq_ld)"""),
    ],
    'site_ge_inject.py': [
        ("""    return place(_ua_speed_base_inject(source))""",
         """    return place(_ua_speed_base_inject(source))

# SPEED-002: phone-size copies of the home stage pictures.
_ua_speed2_base_inject = inject_html
def inject_html(source):
    from ua_stage_images import apply
    return apply(_ua_speed2_base_inject(source))"""),
    ],
}
DEPENDENCY_SHA256 = {}


def targets(root):
    """Existing files the candidate replaces (new modules and picture copies are added beside them)."""
    root = Path(root)
    pages = CATALOG_PAGES + HOME_PAGES + ORDER_PAGES
    return tuple(EDITS) + tuple(name for name in pages if (root/name).is_file())


def edit(name, value):
    text = value.decode('utf-8')
    if 'SPEED-002' in text:
        raise ValueError('SPEED2_ALREADY_APPLIED:' + name)
    for old, new in EDITS[name]:
        if text.count(old) != 1:
            raise ValueError('SPEED2_EDIT:%s:%d' % (name, text.count(old)))
        text = text.replace(old, new)
    return text.encode('utf-8')


def defer_styles(html):
    """The later blocks' style links load without blocking; exactly the five, each once."""
    found = STYLE_LINK.findall(html)
    if sorted(name for _, name in found) != sorted(LATER_STYLES):
        raise ValueError('SPEED2_STYLES:found=' + ','.join(name for _, name in found))
    return STYLE_LINK.sub(lambda m: '<link rel="stylesheet" href="%s" media="print" onload="this.media=\'all\'">'
                          '<noscript><link rel="stylesheet" href="%s"></noscript>' % (m[1], m[1]), html)


def build(source, dependencies, read_original):
    """read_original(url) gives the bytes of a /video/ picture on the server, or None."""
    import ua_card_urls
    import ua_stage_images
    result = {name: (HERE/name).read_bytes() for name in NEW_MODULES}
    copies = {}

    def plan_copy(url):
        data = read_original(url)
        made = ua_stage_images.small(data) if data else None
        if not made:
            return None
        copies[ua_stage_images.copy_url(url)[1:]] = made[0]  # 'video/opt/s/...'
        return ua_stage_images.copy_url(url), made[1]

    for name, value in source.items():
        text = value.decode('utf-8') if not name.endswith('.py') else None
        if name in EDITS:
            changed = edit(name, value)
        elif name in CATALOG_PAGES:
            changed = ua_card_urls.catalog_links(text).encode('utf-8')
        elif name in HOME_PAGES:
            changed = ua_stage_images.apply(text, find=plan_copy).encode('utf-8')
        else:
            changed = defer_styles(text).encode('utf-8')
        if changed == value:
            raise ValueError('SPEED2_UNCHANGED:' + name)
        result[name] = changed
    for relative, data in copies.items():
        result[relative] = data
    return result
