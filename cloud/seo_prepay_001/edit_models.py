"""ua_seo_order_models (SEO-PREPAY-001): the Japan custom-order page — the second «how we work» step and the «how to
order a car from Japan» answer say «service 600 $ + prepayment 1 000 $» like every custom order (owner; no
«депозит» on the site). uk and ru. Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_order_models.py'

EDITS = (
    ("               'Укладаємо договір; ціна фіксується в договорі, депозит 500 $ входить у вартість.',\n",
     "               'Укладаємо договір: послуга — 600 $, передоплата — 1 000 $ (зараховується у вартість авто).',\n"),
    ("               'Заключаем договор; цена фиксируется в договоре, депозит 500 $ входит в стоимость.',\n",
     "               'Заключаем договор: услуга — 600 $, предоплата — 1 000 $ (засчитывается в стоимость авто).',\n"),
    ('а після погодження укладемо договір; депозит 500 $ входить у вартість.',
     'а після погодження укладемо договір: послуга — 600 $, передоплата — 1 000 $ (зараховується у вартість авто).'),
    ('а после согласования заключим договор; депозит 500 $ входит в стоимость.',
     'а после согласования заключим договор: услуга — 600 $, предоплата — 1 000 $ (засчитывается в стоимость авто).'),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('MODELS_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
