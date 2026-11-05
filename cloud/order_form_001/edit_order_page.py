"""Order page: the «Оформлення заявки» view opened by step 1 on the home page (podbor.html#zayavka).

Owner 2026-11-05: from step 1 the client sees the heading «Оформлення заявки», chooses a country and gets the one full
application form; the model cards, «Обрати інше авто» and the SEO intro stay on the normal order page (quick SEO entry)
but are not shown in this view. Pure CSS on the URL fragment (:target, :has), no script change: the order script keeps
the fragment in every address it writes. The heading text comes from order-strings.json like every label of the page;
the script version is raised so browsers load the new strings. Each original fragment must occur exactly once and an
applied fragment is refused.
"""
from release_constants import PAGE, STRINGS

ANCHOR = 'zayavka'
CSS = ('<style id="ua-order-zayavka-001">'
       '#zayavka{display:none}#zayavka:target{display:block}'
       'body:has(#zayavka:target) #model-section,body:has(#zayavka:target) #ua-seo-order-intro{display:none!important}'
       '</style>')
EDITS = {
    PAGE: (
        ('order/order.js?v=20261103.1', 'order/order.js?v=20261105.1'),
        ('<h1 data-label="title">Авто під замовлення</h1>\n',
         '<h1 data-label="title">Авто під замовлення</h1>\n'
         '    <h2 id="zayavka" data-label="application_title">Оформлення заявки</h2>\n'),
        ('</head>', CSS + '</head>'),
    ),
    STRINGS: (
        ('    "title": "Авто під замовлення",\n',
         '    "title": "Авто під замовлення",\n    "application_title": "Оформлення заявки",\n'),
        ('    "title": "Авто под заказ",\n',
         '    "title": "Авто под заказ",\n    "application_title": "Оформление заявки",\n'),
        ('    "title": "ავტომობილი შეკვეთით",\n',
         '    "title": "ავტომობილი შეკვეთით",\n    "application_title": "განაცხადის გაფორმება",\n'),
    ),
}
# Public proof that each file is live.
CHECK_PAGE = 'id="zayavka"'
CHECK_STRINGS = '"application_title": "Оформлення заявки"'


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
