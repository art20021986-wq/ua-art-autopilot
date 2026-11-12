"""ua_seo_landings (SEO-UKRAINE-PAGE-001): the custom-order page links the all-Ukraine page and states the Korea
auction terms of the home page (owner 2026-11-12: auction order — service 600 $ + prepayment 1 000 $; 500 $ is the
prepayment of catalogue cars only).

- order_steps gets the page's address function, as hub() already does (the all-Ukraine link);
- the custom-order page's description, first question and «can the price change» answer name 600 $ + 1 000 $ instead of «депозит 500 $»;
- the custom-order page no longer repeats the generic «Як ми працюємо» list (it says «депозит 500 $» and duplicates
  «Як проходить замовлення»); its order button stays.
The Korea hub and model pages (catalogue cars, 500 $) are unchanged. Each fragment must occur exactly once and an
applied edit is refused.
"""
NAME = 'ua_seo_landings.py'
EDITS = (
    ('hub_texts.order_steps(lang), ', "hub_texts.order_steps(lang, lambda key: '/video/' + path(lang, key)), "),
    ('доставка й розмитнення. Ціна фіксується в договорі, депозит 500 $ входить у вартість.',
     'доставка й розмитнення. Замовлення з аукціону в Кореї: послуга 600 $ і передоплата 1 000 $.'),
    ('доставка и растаможка. Цена фиксируется в договоре, депозит 500 $ входит в стоимость.',
     'доставка и растаможка. Заказ с аукциона в Корее: услуга 600 $ и предоплата 1 000 $.'),
    ('а після погодження укладемо договір; депозит 500 $ входить у вартість.',
     'а після погодження укладемо договір: послуга 600 $ і передоплата 1 000 $ (зараховується у вартість авто).'),
    ('а после согласования заключим договор; депозит 500 $ входит в стоимость.',
     'а после согласования заключим договор: услуга 600 $ и предоплата 1 000 $ (засчитывается в стоимость авто).'),
    ('Ні. Ціна фіксується в договорі до купівлі та не змінюється, депозит 500 $ входить у вартість.',
     'Ні. Ціни на логістику фіксовані, автомобіль — за ціною аукціону, митні платежі — офіційні, їх суми ви '
     'отримуєте заздалегідь.'),
    ('Нет. Цена фиксируется в договоре до покупки и не меняется, депозит 500 $ входит в стоимость.',
     'Нет. Цены на логистику фиксированы, автомобиль — по цене аукциона, таможенные платежи — официальные, их '
     'суммы вы получаете заранее.'),
    ("escape(order_models.JAPAN[lang]['link']), examples, _process(lang), t['faq_title'],",
     "escape(order_models.JAPAN[lang]['link']), examples,\n"
     "        '<a class=\"cta\" href=\"/video/podbor.html\">%s</a>' % escape(t['cta']), t['faq_title'],"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('LANDINGS_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
