"""Order page, Japan: a short note under every card (JAPAN-NOTE-001).

Owner request 2026-10-30 («Да»): Japan models are shown with the right-hand drive and are converted to the
left-hand drive by colleagues in Georgia; the classics are bought with the left-hand drive only.
The note text is data in order-strings.json, keyed note_<country>_<kind>: order.js shows it under a card only
when such a key exists, so other countries stay as they are. The look is the new model-note.css.
The order.js version on the page is raised so browsers load the new module and strings.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
import re

import note_assets

PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'
VERSION = '20261030.1'

NOTES = {
    'uk': ('Праве кермо, як продають у Японії, переробляють на ліве кермо наші колеги в Грузії. Понад 20 років досвіду.',
           'Ретро-авто купуємо тільки з лівим кермом.'),
    'ru': ('Правый руль, как продают в Японии, переделывают на левый руль наши коллеги в Грузии. Более 20 лет опыта.',
           'Ретро-автомобили покупаем только с левым рулём.'),
    'ka': ('მარჯვენა საჭეს, როგორც იაპონიაში იყიდება, მარცხენა საჭეზე გადააკეთებენ ჩვენი კოლეგები საქართველოში. '
           '20 წელზე მეტი გამოცდილება.',
           'რეტრო ავტომობილებს ვყიდულობთ მხოლოდ მარცხენა საჭით.'),
}
CLOSE = {'uk': 'Закрити', 'ru': 'Закрыть', 'ka': 'დახურვა'}


def _strings(lang):
    line = '    "quick_close": "%s",\n' % CLOSE[lang]
    model, category = NOTES[lang]
    return line, line + '    "note_japan_model": "%s",\n    "note_japan_category": "%s",\n' % (model, category)


EDITS = {
    PAGE: (
        ('<link rel="stylesheet" href="order/gallery.css?v=20261027.1">',
         '<link rel="stylesheet" href="order/gallery.css?v=20261027.1">'
         '<link rel="stylesheet" href="order/model-note.css?v=%s">' % VERSION),
    ),
    SCRIPT: (
        ("    info.append(offer,button);article.append(media,info);return article;\n",
         "    info.append(offer,button);article.append(media,info);\n"
         "    const note=t('note_'+state.country+'_'+model.kind);\n"
         "    if(note) article.append(node('p',note,'model-note'));\n"
         "    return article;\n"),
    ),
    STRINGS: tuple(_strings(lang) for lang in ('uk', 'ru', 'ka')),
}
SCRIPT_VERSION = re.compile(r'order/order\.js\?v=[0-9.]+')
# Public proof that each file is live.
CHECK_PAGE = 'order/model-note.css?v=' + VERSION
CHECK_SCRIPT = "article.append(node('p',note,'model-note'))"
CHECK_STRINGS = '"note_japan_category": "Ретро-авто купуємо тільки з лівим кермом."'
CHECK_STYLE = '.model-note'


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
