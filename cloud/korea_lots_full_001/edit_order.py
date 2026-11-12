"""Order page: this week's auction lots first in the model photo carousels (KOREA-MODEL-LOTS-001).

Owner 2026-11-12. The server job writes /video/<country>/model-lots.json ({"models": {model key: [lot, ...]}},
korea_auction.model_lots); order.js reads the file of the chosen country (any country: Korea now, others later)
and puts each model's lots before its photos in the card carousel. A lot slide shows a strip with the auction
date, grade, year, mileage and start price; the strip links to the lot card on the auction page. Without the
file, or without lots for a model, the card stays exactly as before.
Small edits of the live files only; each original fragment must occur exactly once and an applied fragment is
refused. The order.js and gallery asset versions are raised so browsers load the new modules.
"""
import re

VERSION = '20261112.1'
PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
GALLERY = 'video/order/gallery.js'
STYLE = 'video/order/gallery.css'
STRINGS = 'video/order/order-strings.json'

LABELS = {  # after "photo_next" of each language
    'uk': ('"photo_next": "Наступне фото",',
           '"auction_lot": "Аукціон", "auction_km": "км", "auction_price_tbd": "ціна — на торгах",'),
    'ru': ('"photo_next": "Следующее фото",',
           '"auction_lot": "Аукцион", "auction_km": "км", "auction_price_tbd": "цена — на торгах",'),
    'ka': ('"photo_next": "შემდეგი ფოტო",',
           '"auction_lot": "აუქციონი", "auction_km": "კმ", "auction_price_tbd": "ფასი — ვაჭრობაზე",'),
}

AUCTION_HELPERS = (
    "// KOREA-MODEL-LOTS-001: this week's auction lots of a model, from /video/<country>/model-lots.json (written\n"
    "// hourly by the country's auction job). Loaded once per country; the model cards are drawn again when it arrives.\n"
    "const auctionLots={};\n"
    "function countryLots(code) {\n"
    "  if(!(code in auctionLots)) {\n"
    "    auctionLots[code]=null;\n"
    "    fetch(`/video/${encodeURIComponent(code)}/model-lots.json`,{cache:'no-cache'})\n"
    "      .then(response=>response.ok?response.json():null).catch(()=>null)\n"
    "      .then(value=>{auctionLots[code]=value;if(value&&state.country===code&&!state.receipt){models();setBusy(state.busy);}});\n"
    "  }\n"
    "  return auctionLots[code];\n"
    "}\n"
    "function auctionSlides(key) {\n"
    "  const number=value=>Number(value).toLocaleString('uk-UA');\n"
    "  return (countryLots(state.country)?.models?.[key]||[]).map(lot=>({path:lot.photo,href:lot.href,caption:[\n"
    "    `${t('auction_lot')} ${lot.date}`+(lot.score?` · ${lot.score}`:''),\n"
    "    `${lot.year} · ${number(lot.km)} ${t('auction_km')} · `+(lot.usd?`$${number(lot.usd)}`:t('auction_price_tbd'))]}));\n"
    "}\n"
)

EDITS = {
    SCRIPT: (
        ("function models() {\n", AUCTION_HELPERS + "function models() {\n"),
        ("    const extra=state.gallery?.models?.[model.key];\n"
         "    if(extra) media.append(gallery(extra.photos,{base:assets,alt:model.media.alt[state.lang],lazy:index>0,\n",
         "    const extra=state.gallery?.models?.[model.key];\n"
         "    const slides=[...auctionSlides(model.key),...(extra?extra.photos:[])];  // auction lots first\n"
         "    if(slides.length) media.append(gallery(slides,{base:assets,alt:model.media.alt[state.lang],lazy:index>0,\n"),
    ),
    GALLERY: (
        ("  let index=0;\n",
         "  // KOREA-MODEL-LOTS-001: an auction lot slide shows its data on a strip that links to the lot card.\n"
         "  const lot=document.createElement('a');\n"
         "  lot.className='gallery-lot';lot.hidden=true;\n"
         "  let index=0;\n"),
        ("    img.src=url(index);img.width=photo.width;img.height=photo.height;\n",
         "    img.src=url(index);\n"
         "    if(photo.width) {img.width=photo.width;img.height=photo.height;}\n"
         "    else {img.removeAttribute('width');img.removeAttribute('height');}\n"
         "    box.classList.toggle('gallery-has-lot',Boolean(photo.href));\n"
         "    lot.hidden=!photo.href;\n"
         "    if(photo.href) {\n"
         "      lot.href=photo.href;\n"
         "      lot.replaceChildren(...photo.caption.map(text=>{const line=document.createElement('span');line.textContent=text;return line;}));\n"
         "    }\n"),
        ("  box.append(img);\n", "  box.append(img,lot);\n"),
    ),
    STRINGS: tuple((old, old + ' ' + new) for old, new in LABELS.values()),
}
# gallery.css: new rules appended (the strip above the arrow halves; the counter moves up on a lot slide).
STYLE_RULES = (
    '\n/* KOREA-MODEL-LOTS-001: auction lot slide */\n'
    '.ua-order .gallery-lot { position:absolute; left:0; right:0; bottom:0; z-index:1; display:flex; flex-direction:column;'
    ' gap:1px; padding:6px 10px; background:rgba(11,28,45,.82); color:#f4f5f7; font-size:13px; line-height:1.35;'
    ' text-decoration:none; }\n'
    '.ua-order .gallery-lot span:first-child { color:#ffd23f; font-weight:600; }\n'
    '.ua-order .gallery-lot:hover, .ua-order .gallery-lot:focus-visible { background:rgba(11,28,45,.95); }\n'
    '.ua-order .gallery-has-lot .gallery-count { top:8px; bottom:auto; }\n'
    '.ua-order .gallery-has-lot > button { bottom:44px; height:auto; }\n'
    '@media(max-width:640px) { .ua-order .gallery-lot { padding:4px 8px; font-size:11px; }'
    ' .ua-order .gallery-has-lot .gallery-count { top:6px; } .ua-order .gallery-has-lot > button { bottom:36px; } }\n'
)
APPLIED = {PAGE: None, SCRIPT: 'function countryLots(code)', GALLERY: "lot.className='gallery-lot'",
           STYLE: 'KOREA-MODEL-LOTS-001', STRINGS: '"auction_lot": '}
SCRIPT_TAG = re.compile(r'order/order\.js\?v=[0-9.]+')
GALLERY_CSS_TAG = re.compile(r'order/gallery\.css\?v=[0-9.]+')
GALLERY_JS_TAG = re.compile(r"\./gallery\.js\?v=[0-9.]+")
SOURCE_FILES = (PAGE, SCRIPT, GALLERY, STYLE, STRINGS)
# Public proof that each file is live.
CHECKS = {PAGE: 'order/order.js?v=' + VERSION, SCRIPT: "./gallery.js?v=" + VERSION, GALLERY: "lot.className='gallery-lot'",
          STYLE: '.gallery-has-lot', STRINGS: '"auction_lot": "Аукціон"'}


def _versions(name, text):
    """The asset versions this release raises: order.js and gallery.css on the page, gallery.js in order.js."""
    if name == PAGE:
        if len(SCRIPT_TAG.findall(text)) != 1 or len(GALLERY_CSS_TAG.findall(text)) not in (1, 2):
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = SCRIPT_TAG.sub('order/order.js?v=' + VERSION, text)
        return GALLERY_CSS_TAG.sub('order/gallery.css?v=' + VERSION, text)
    if name == SCRIPT:
        if len(GALLERY_JS_TAG.findall(text)) != 1:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        return GALLERY_JS_TAG.sub('./gallery.js?v=' + VERSION, text)
    return text


def build(name, source):
    """One live file with this release applied."""
    text = source.decode('utf-8')
    marker = APPLIED[name]
    if (marker and marker in text) or (name == PAGE and 'order/order.js?v=' + VERSION in text):
        raise ValueError('ORDER_ALREADY_APPLIED:' + name)
    for old, new in EDITS.get(name, ()):
        if text.count(old) != 1:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    if name == STYLE:
        text = text.rstrip('\n') + '\n' + STYLE_RULES
    return _versions(name, text).encode('utf-8')
