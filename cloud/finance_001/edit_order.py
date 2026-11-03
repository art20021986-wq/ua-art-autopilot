"""Order page (FINANCE-001): «Розрахувати» on every model card becomes the «Кредити та лізинг» link.

order.js: the card's calculate button is replaced by a link to the finance page (a real <a href>, so search
engines follow it and a visitor can open it in a new tab) with the model and country, which the CRM bot
shows as where the visit came from. order-strings.json: the link text and the page address per language
(uk/ru/ka, from ua_finance_partners) take the place of the unused «calculate» text. podbor.html: the link's
look (finance-link.css) and the raised order.js version, so browsers load the new module and texts.
The other ways to the order form (the «other car» form, ?model= links) are unchanged.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
import json
import re

import ua_finance_partners as finance

PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'
VERSION = '20261103.1'
CALCULATE = {'uk': 'Розрахувати', 'ru': 'Рассчитать', 'ka': 'გამოთვლა'}


def _strings(lang):
    old = '    "calculate": %s,\n' % json.dumps(CALCULATE[lang], ensure_ascii=False)
    new = '    "finance": %s,\n    "finance_href": %s,\n' % (
        json.dumps(finance.BUTTON[lang], ensure_ascii=False), json.dumps(finance.page_path(lang)))
    return old, new


EDITS = {
    PAGE: (
        ('<link rel="stylesheet" href="order/model-price.css?v=20261031.1">',
         '<link rel="stylesheet" href="order/model-price.css?v=20261031.1">'
         '<link rel="stylesheet" href="order/finance-link.css?v=%s">' % VERSION),
    ),
    SCRIPT: (
        ("    const button=node('button',t('calculate'));button.type='button';"
         "button.addEventListener('click',()=>selectModel(model.key));\n",
         "    const button=node('a',t('finance'),'button finance-link');\n"
         "    button.href=`${t('finance_href')}?model=${encodeURIComponent(model.key)}&strana=${encodeURIComponent(state.country)}`;\n"),
    ),
    STRINGS: tuple(_strings(lang) for lang in ('uk', 'ru', 'ka')),
}
SCRIPT_VERSION = re.compile(r'order/order\.js\?v=[0-9.]+')
# Public proof that each file is live.
CHECK_PAGE = 'order/finance-link.css?v=' + VERSION
CHECK_SCRIPT = "node('a',t('finance'),'button finance-link')"
CHECK_STRINGS = '"finance": "Кредити та лізинг"'


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
    if name == STRINGS:
        json.loads(text)
    return text.encode('utf-8')
