"""Order page: model photo gallery and generation line (MODEL-GALLERY-001).

Owner request 2026-10-26. New files (gallery.js, gallery.css, model-gallery.json, photos) come from
this package; the existing files get only these small edits. order.js loads model-gallery.json next
to its strings; when it is missing or fails, the model cards stay exactly as before. A model with
gallery data shows the photo switcher, its generation after the name and no «under order» tag. Built on top of the live
PODBOR-MODEL-001 files; the order.js version on the page is replaced whatever it is (another release may
have raised it), so browsers load the new module. Each original fragment must occur exactly once and
an applied fragment is refused. On files that already carry an earlier gallery release only the asset
versions are raised (new photos, owner 2026-10-27); the strings stay as they are.
"""

import re

VERSION = '20261027.1'
PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'

LABELS = {
    'uk': ('"under_order": "Під замовлення",',
           '"gallery": "фотогалерея", "photo_prev": "Попереднє фото", "photo_next": "Наступне фото",'),
    'ru': ('"under_order": "Под заказ",',
           '"gallery": "фотогалерея", "photo_prev": "Предыдущее фото", "photo_next": "Следующее фото",'),
    'ka': ('"under_order": "შეკვეთით",',
           '"gallery": "ფოტოგალერეა", "photo_prev": "წინა ფოტო", "photo_next": "შემდეგი ფოტო",'),
}

EDITS = {
    PAGE: (
        ('<link rel="stylesheet" href="order/order.css?v=20261025.2">',
         '<link rel="stylesheet" href="order/order.css?v=20261025.2">'
         '<link rel="stylesheet" href="order/gallery.css?v=' + VERSION + '">'),
    ),
    SCRIPT: (
        ("import {PreferenceForm} from './preferences-form.js?v=20260927.10';\n",
         "import {PreferenceForm} from './preferences-form.js?v=20260927.10';\n"
         "import {gallery} from './gallery.js?v=" + VERSION + "';\n"),
        ("const state={catalog:null,strings:null,",
         "const state={catalog:null,strings:null,gallery:null,"),
        ("    const media=node('div',undefined,'model-media');\n"
         "    if(model.media.approval==='approved' && model.media.path) {\n",
         "    const media=node('div',undefined,'model-media');\n"
         "    const extra=state.gallery?.models?.[model.key];\n"
         "    if(extra) media.append(gallery(extra.photos,{base:assets,alt:model.media.alt[state.lang],lazy:index>0,\n"
         "      labels:{gallery:t('gallery'),prev:t('photo_prev'),next:t('photo_next')}}));\n"
         "    else if(model.media.approval==='approved' && model.media.path) {\n"),
        ("    info.append(node('h3',model.labels[state.lang]),node('span',t('under_order'),'tag'));\n",
         "    // A card with gallery data: the generation continues the name; «under order» is the page title already.\n"
         "    const title=node('h3',model.labels[state.lang]);\n"
         "    if(extra) title.append(' ',node('span',extra.generation[state.lang],'generation'));\n"
         "    info.append(title);\n"
         "    if(!extra) info.append(node('span',t('under_order'),'tag'));\n"),
        ("  const [bootstrap,strings]=await Promise.all([fetch('/api/orders/bootstrap',{credentials:'same-origin'}),"
         "fetch(new URL('order-strings.json'+new URL(import.meta.url).search,assets)),pageReady]);\n",
         "  // Gallery data is optional: without it the model cards keep their single photo.\n"
         "  const galleryData=fetch(new URL('model-gallery.json'+new URL(import.meta.url).search,assets))\n"
         "    .then(response=>response.ok?response.json():null).catch(()=>null);\n"
         "  const [bootstrap,strings,galleryValue]=await Promise.all([fetch('/api/orders/bootstrap',{credentials:'same-origin'}),"
         "fetch(new URL('order-strings.json'+new URL(import.meta.url).search,assets)),galleryData,pageReady]);\n"),
        ("state.strings=await strings.json();\n",
         "state.strings=await strings.json();state.gallery=galleryValue;\n"),
    ),
    STRINGS: tuple((old, old + ' ' + new) for old, new in LABELS.values()),
}
# Public proof that each file is live.
CHECK_PAGE = 'order/order.js?v=' + VERSION
CHECK_SCRIPT = "import {gallery} from './gallery.js?v=" + VERSION + "';"
CHECK_STRINGS = '"photo_next": "Наступне фото"'


# The page's order.js version, set by pattern: exactly one module script tag.
SCRIPT_TAG = re.compile(r'order/order\.js\?v=[0-9.]+')
# An earlier gallery release: its marker in each file and its asset version tags.
APPLIED = {PAGE: 'order/gallery.css?v=', SCRIPT: "import {gallery} from './gallery.js?v=", STRINGS: '"photo_next": '}
GALLERY_TAG = re.compile(r'(order/gallery\.css|\./gallery\.js)\?v=[0-9.]+')


def build(name, source):
    text = source.decode('utf-8')
    if name == PAGE:
        if len(SCRIPT_TAG.findall(text)) != 1 or 'order/order.js?v=' + VERSION in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = SCRIPT_TAG.sub('order/order.js?v=' + VERSION, text)
    if APPLIED[name] in text:
        if name != STRINGS:
            if len(GALLERY_TAG.findall(text)) != 1 or GALLERY_TAG.search(text).group(0).endswith('?v=' + VERSION):
                raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
            text = GALLERY_TAG.sub(lambda match: match.group(1) + '?v=' + VERSION, text)
        return text.encode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
