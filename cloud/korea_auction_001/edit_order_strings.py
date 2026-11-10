"""video/order/order-strings.json: the selection page heading becomes «Індивідуальне замовлення автомобіля»
(owner 2026-11-10: two clearly different ways — online auctions and the individual order).

Only the 'title' string of each language changes, and only from its known current value.
"""
import json

PATH = 'video/order/order-strings.json'
TITLES = {
    'uk': ('Авто під замовлення', 'Індивідуальне замовлення автомобіля'),
    'ru': ('Авто под заказ', 'Индивидуальный заказ автомобиля'),
    'ka': ('ავტომობილი შეკვეთით', 'ავტომობილის ინდივიდუალური შეკვეთა'),
}


def build(source):
    """Replace exactly the three title lines; the rest of the file stays byte for byte."""
    text = source.decode('utf-8')
    for lang, (old, new) in TITLES.items():
        line = '"title": %s' % json.dumps(old, ensure_ascii=False)
        if text.count(line) != 1 or json.loads(text)[lang].get('title') != old:
            raise ValueError('ORDER_TITLE_UNEXPECTED:' + lang)
        text = text.replace(line, '"title": %s' % json.dumps(new, ensure_ascii=False))
    json.loads(text)
    return text.encode('utf-8')
