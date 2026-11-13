"""ua_seo_landings (SEO-PREPAY-001): ordering a car from a Korean auction is «service 600 $ + prepayment 1 000 $»
(owner 2026-11-12/13); 500 $ stays only for catalogue cars (the hub description). Changes the second «how we work»
step and the «how to order a car from Korea» answer (text and FAQPage), uk and ru. Each original fragment must
occur exactly once and an applied fragment is refused.
"""
NAME = 'ua_seo_landings.py'

EDITS = (
    ('Укладаємо договір; ціна фіксується в договорі, депозит 500 $ входить у вартість.',
     'Укладаємо договір: послуга — 600 $, передоплата — 1 000 $ (зараховується у вартість авто).'),
    ('Заключаем договор; цена фиксируется в договоре, депозит 500 $ входит в стоимость.',
     'Заключаем договор: услуга — 600 $, предоплата — 1 000 $ (засчитывается в стоимость авто).'),
    ('й укладаємо договір. Ціна фіксується в договорі, депозит 500 $ входить у вартість.',
     'й укладаємо договір: послуга — 600 $, передоплата — 1 000 $ (зараховується у вартість авто).'),
    ('и заключаем договор. Цена фиксируется в договоре, депозит 500 $ входит в стоимость.',
     'и заключаем договор: услуга — 600 $, предоплата — 1 000 $ (засчитывается в стоимость авто).'),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('LANDINGS_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
