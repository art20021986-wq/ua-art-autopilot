"""Drop the large first-screen phrase; the small line above it becomes the page's h1 (HOME-HEADING-001).

Owner-approved 2026-10-25: «Авто під замовлення під ключ» is removed in uk/ru/ka and
«АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ» stays as it looks but is the h1, so the page
keeps one main heading. The large-heading CSS of this block is reduced to a zero margin.
Each original fragment must occur exactly once, otherwise nothing is changed.
"""

EDITS = (
    ('<span class="eyebrow" data-ru="АВТО ПОД ЗАКАЗ · УКРАИНА И ГРУЗИЯ" data-uk="АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ" '
     'data-ka="ავტომობილი შეკვეთით · საქართველო და უკრაინა">АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ</span>'
     '<h1><span data-ru="Авто под заказ" data-uk="Авто під замовлення" data-ka="ავტომობილი შეკვეთით">Авто під замовлення</span>'
     '<br><span data-ru="под ключ" data-uk="під ключ" data-ka="სრული მომსახურებით">під ключ</span></h1>',
     '<h1 class="eyebrow" data-ru="АВТО ПОД ЗАКАЗ · УКРАИНА И ГРУЗИЯ" data-uk="АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ" '
     'data-ka="ავტომობილი შეკვეთით · საქართველო და უკრაინა">АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ</h1>'),
    ('.ua-order-copy h1{margin:0;font-size:clamp(34px,3.6vw,48px);line-height:1.04;letter-spacing:-1.4px}\n',
     '.ua-order-copy h1{margin:0}\n'),
    ('.ua-order-copy h1{font-size:32px}\n', ''),
)
# Public proof that the new heading is live.
CHECK = '>АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ</h1>'


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1:
            raise ValueError('HOME_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
