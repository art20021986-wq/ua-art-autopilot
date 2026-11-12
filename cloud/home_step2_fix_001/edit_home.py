"""Step 2 (HOME-STEP2-FIX-001, owner 2026-11-12): the old «Підбираємо, перевіряємо і купуємо…» line becomes the
owner-approved service text (Korea), and the other countries' step 2 title «Підбір і перевірка» becomes
«Супровід автомобіля». Every other byte stays. The home page must hold each anchor exactly once; video/korea.html
(its no-JS copy of the steps block) changes only where it holds them. Otherwise nothing is changed.
"""
import html

import service_text as T

OLD = ('<p data-ru="Подбираем, проверяем и покупаем автомобиль на корейских аукционах." '
       'data-uk="Підбираємо, перевіряємо і купуємо автомобіль на корейських аукціонах." '
       'data-ka="ვარჩევთ, ვამოწმებთ და ვყიდულობთ ავტომობილს კორეის აუქციონებზე.">'
       'Підбираємо, перевіряємо і купуємо автомобіль на корейських аукціонах.</p>')
PAY = ('<p class="ua-step-pay" data-ru="Стоимость услуги — 600 $" data-uk="Вартість послуги — 600 $" '
       'data-ka="მომსახურების ღირებულება — 600 $">Вартість послуги — 600 $</p>')
OLD_TITLE = ('<b data-ru="Подбор и проверка" data-uk="Підбір і перевірка" data-ka="შერჩევა და შემოწმება">'
             'Підбір і перевірка</b>')
# Public proof: the old words are gone and the new text is there.
GONE = ('корейських аукціонах', 'Підбір і перевірка')
STEP2 = 'data-uk="Оформлення договору"'


def text(tag, words, attrs=''):
    ru, uk, ka = (html.escape(w, quote=True) for w in words)
    if any(w != html.escape(w, quote=True) for w in words):
        raise ValueError('HOME_STEP2_TEXT')
    return '<%s%s data-ru="%s" data-uk="%s" data-ka="%s">%s</%s>' % (tag, attrs, ru, uk, ka, uk, tag)


SERVICE = (text('p', T.FIRST) + text('p', T.INCLUDES)
           + '<ul style="list-style:disc;margin:4px 0 0;padding-left:20px">%s</ul>' % ''.join(text('li', i) for i in T.ITEMS))
SEPARATE = text('p', T.SEPARATE)
NEW_TITLE = text('b', T.OTHER_TITLE)
CHECK = text('p', T.FIRST)


def build(source, required=True):
    page = source.decode('utf-8')
    old, title, pay = page.count(OLD), page.count(OLD_TITLE), page.count(PAY)
    if old > 1 or title > 1 or (old and pay != 1) or CHECK in page:
        raise ValueError('HOME_STEP2_ANCHOR')
    if required and (old != 1 or title != 1 or page.count(STEP2) != 1):
        raise ValueError('HOME_STEP2_ANCHOR')
    if not old and not title:
        return None
    if old:
        page = page.replace(OLD, SERVICE, 1).replace(PAY, PAY + SEPARATE, 1)
    if title:
        page = page.replace(OLD_TITLE, NEW_TITLE, 1)
    return page.encode('utf-8')
