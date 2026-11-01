"""Build the SPEED-001 candidate: faster mobile pages, same content (owner «Да» 2026-11-01).

Lighthouse (PAGESPEED-PROBE-20261101-R2): Telegram's script in <head> blocks the first paint of cards and the
order page (~1.5 s); the card gallery's thumbnails load the 1000 px photo copies (−2.5 MB on a card); model
pages show full photos in small tiles (−1.1 MB). Changes, each in its own module:
- ua_tg_script.py (new): moves the Telegram script to just before its first user; site_ge_inject.inject_html,
  which every page writer already calls, runs it; the order pages already written get it now.
- ua_photo_copies.py (new): finds the s/ (440 px) and m/ (1000 px) copies the card generator already makes.
- ua_media_gallery.py: thumbnails use the s/ copy. ua_seo_landings.py: car tiles use m/ with an s/+m/ srcset.
- ua_seo_metadata.py: SEO_REVISION bump, so the existing CRM sync republishes every card once with the above.
Texts, photo order, CRM data and every other byte stay as they are.
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW_MODULES = ('ua_tg_script.py', 'ua_photo_copies.py')
PAGES = ('video/podbor.html', 'site/podbor.html')
REVISION = ("SEO_REVISION = 'SEO-CONTENT-001'", "SEO_REVISION = 'SPEED-001'")
EDITS = {
    'ua_media_gallery.py': [
        ('from ua_media_script import JS\n',
         'from ua_media_script import JS\nfrom ua_photo_copies import copy as photo_copy\n'),
        ("""        if item['preview']:
            out.append(f'<img src="{esc(item["preview"])}" alt="" loading="lazy" decoding="async" fetchpriority="low" draggable="false">')""",
         """        if item['preview']:
            thumb = (photo_copy(item['preview'], 's') if is_photo else None) or item['preview']  # SPEED-001
            out.append(f'<img src="{esc(thumb)}" alt="" loading="lazy" decoding="async" fetchpriority="low" draggable="false">')"""),
    ],
    'ua_seo_landings.py': [
        ('import ua_seo_order_models as order_models\n',
         'import ua_photo_copies as photo_copies\nimport ua_seo_order_models as order_models\n'),
        ("""def _car_list(cars, lang):""",
         """# SPEED-001: tiles are one column on a phone and ~250 px wide from two columns up.
TILE_SIZES = '(max-width: 520px) calc(100vw - 32px), 260px'


def _tile_srcset(image):
    value = photo_copies.srcset(image)
    return ' srcset="%s" sizes="%s"' % (escape(value), TILE_SIZES) if value else ''


def _car_list(cars, lang):"""),
        ("""        image = ('<img src="%s" alt="%s" loading="%s" decoding="async">' % (
            escape(c['image']), escape(c['name']), 'eager' if i == 0 else 'lazy')) if c.get('image') else ''""",
         """        image = ('<img src="%s"%s alt="%s" loading="%s" decoding="async">' % (
            escape(photo_copies.copy(c['image'], 'm') or c['image']), _tile_srcset(c['image']), escape(c['name']),
            'eager' if i == 0 else 'lazy')) if c.get('image') else ''"""),
    ],
    'ua_seo_metadata.py': [REVISION],
    'site_ge_inject.py': [
        ('    return render(_ua_price_base_inject(source))',
         """    return render(_ua_price_base_inject(source))

# SPEED-001: Telegram's script just before its first user, not in <head>.
_ua_speed_base_inject = inject_html
def inject_html(source):
    from ua_tg_script import place
    return place(_ua_speed_base_inject(source))"""),
    ],
}
DEPENDENCY_SHA256 = {}


def targets(root):
    """Existing files the candidate replaces (the new modules are added beside them)."""
    root = Path(root)
    return tuple(EDITS) + tuple(name for name in PAGES if (root/name).is_file())


def edit(name, value):
    text = value.decode('utf-8')
    if 'SPEED-001' in text:
        raise ValueError('SPEED_ALREADY_APPLIED:' + name)
    for old, new in EDITS[name]:
        if text.count(old) != 1:
            raise ValueError('SPEED_EDIT:%s:%d' % (name, text.count(old)))
        text = text.replace(old, new)
    return text.encode('utf-8')


def build(source, dependencies):
    import ua_tg_script
    result = {name: (HERE/name).read_bytes() for name in NEW_MODULES}
    for name, value in source.items():
        if name in EDITS:
            result[name] = edit(name, value)
        else:
            moved = ua_tg_script.place(value.decode('utf-8')).encode('utf-8')
            if moved == value:
                raise ValueError('SPEED_PAGE_UNCHANGED:' + name)
            result[name] = moved
    return result
