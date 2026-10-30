"""Order page, Korea and Japan: a price line in every card (KOREA-JAPAN-PRICE-001).

Owner request 2026-10-30 («Да»): six models get «from N $ to Kyiv with a certificate, no extra payments»,
the other Japan cards get «price on request». The texts are data in order-strings.json: price_<model key> for
a model, price_<country> for the rest of that country's cards; order.js shows the line only when a text exists,
so other countries stay as they are. The look is the new model-price.css.
The order.js version on the page is raised so browsers load the new module and strings.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
import json
import re

PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'
VERSION = '20261031.1'

# USD from Korea and Japan to Kyiv, owner 2026-10-30.
PRICES = {'kia-k5': 17400, 'hyundai-sonata': 17600, 'hyundai-tucson': 19500, 'kia-sportage': 21400,
          'hyundai-santa-fe': 19700, 'nissan-note': 15400}
FALLBACK = ('japan',)
FROM = {'uk': 'Від %s $ до Києва з сертифікатом, без додаткових платежів.',
        'ru': 'От %s $ до Киева с сертификатом, без дополнительных платежей.',
        'ka': '%s $-დან კიევამდე, სერტიფიკატით, დამატებითი გადასახადების გარეშე.'}
ON_REQUEST = {'uk': 'Ціна уточнюється.', 'ru': 'Цена уточняется.', 'ka': 'ფასი ზუსტდება.'}
# Anchor per language: the last note line (JAPAN-NOTE-001).
ANCHOR = {'uk': 'Ретро-авто купуємо тільки з лівим кермом.', 'ru': 'Ретро-автомобили покупаем только с левым рулём.',
          'ka': 'რეტრო ავტომობილებს ვყიდულობთ მხოლოდ მარცხენა საჭით.'}


def amount(value):
    """17400 -> '17 400' with a non-breaking space, so the number never wraps."""
    return '{:,}'.format(value).replace(',', ' ')


def texts(lang):
    value = {'price_' + key: FROM[lang] % amount(usd) for key, usd in PRICES.items()}
    value.update({'price_' + country: ON_REQUEST[lang] for country in FALLBACK})
    return value


def _strings(lang):
    line = '    "note_japan_category": "%s",\n' % ANCHOR[lang]
    added = ''.join('    "%s": %s,\n' % (k, json.dumps(v, ensure_ascii=False)) for k, v in texts(lang).items())
    return line, line + added


EDITS = {
    PAGE: (
        ('<link rel="stylesheet" href="order/model-note.css?v=20261030.1">',
         '<link rel="stylesheet" href="order/model-note.css?v=20261030.1">'
         '<link rel="stylesheet" href="order/model-price.css?v=%s">' % VERSION),
    ),
    SCRIPT: (
        ("    info.append(offer,button);article.append(media,info);\n",
         "    info.append(offer,button);article.append(media,info);\n"
         "    const price=t('price_'+model.key)??t('price_'+state.country);\n"
         "    if(price) article.append(node('p',price,'model-price'));\n"),
    ),
    STRINGS: tuple(_strings(lang) for lang in ('uk', 'ru', 'ka')),
}
SCRIPT_VERSION = re.compile(r'order/order\.js\?v=[0-9.]+')
# Public proof that each file is live.
CHECK_PAGE = 'order/model-price.css?v=' + VERSION
CHECK_SCRIPT = "article.append(node('p',price,'model-price'))"
CHECK_STRINGS = '"price_kia-k5": "Від 17 400 $ до Києва'
CHECK_STYLE = '.model-price'


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    if name == PAGE:
        current = SCRIPT_VERSION.findall(text)
        if len(current) != 1 or current[0] == 'order/order.js?v=' + VERSION:
            raise ValueError('ORDER_SCRIPT_VERSION:' + name)
        text = SCRIPT_VERSION.sub('order/order.js?v=' + VERSION, text)
    return text.encode('utf-8')
