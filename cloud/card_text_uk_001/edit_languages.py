"""Site language script (video/ua-site-languages.js), CARD-TEXT-UK-001: one Ukrainian phrase for UA-0015.

The Ukrainian card version is derived from the site's own dictionary (ua_card_lang); a card with a phrase that has
no Ukrainian is not derived. UA-0015's CRM description has one such sentence (FINANCE-PREFLIGHT CARD-FINANCE2 R2),
so its Ukrainian and Russian versions stopped updating on 2026-11-02. The sentence and its Ukrainian join the "uk"
dictionary; nothing else changes. The edit refuses a second application.
"""
import json

NAME = 'video/ua-site-languages.js'
RUSSIAN = ('Пробег 291 400 км указан честно и без попыток что-либо скрыть. Поэтому мы предлагаем оценивать автомобиль '
           'не по красивым обещаниям, а по фактическим материалам технического, кузовного и визуального осмотра.')
UKRAINIAN = ('Пробіг 291 400 км вказано чесно й без спроб щось приховати. Тому ми пропонуємо оцінювати автомобіль '
             'не за гарними обіцянками, а за фактичними матеріалами технічного, кузовного та візуального огляду.')
ANCHOR = '"uk":{'
ENTRY = '%s:%s,' % (json.dumps(RUSSIAN, ensure_ascii=False), json.dumps(UKRAINIAN, ensure_ascii=False))


def build(source):
    text = source.decode('utf-8')
    if text.count(ANCHOR) != 1 or ENTRY in text:
        raise ValueError('LANGUAGES_FRAGMENT')
    return text.replace(ANCHOR, ANCHOR + ENTRY).encode('utf-8')
