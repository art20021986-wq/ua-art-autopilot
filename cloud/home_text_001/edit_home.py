"""Remove the Kyiv binding from the first-screen labels of the home page (HOME-TEXT-001).

Only the eyebrow and the second heading line change; every other byte stays as is.
Each original label must occur exactly once, otherwise nothing is changed.
"""

EDITS = (
    ('<span class="eyebrow" data-ru="АВТО ПОД ЗАКАЗ · КИЕВ" data-uk="АВТО ПІД ЗАМОВЛЕННЯ · КИЇВ" '
     'data-ka="ავტომობილი შეკვეთით · კიევი">АВТО ПІД ЗАМОВЛЕННЯ · КИЇВ</span>',
     '<span class="eyebrow" data-ru="АВТО ПОД ЗАКАЗ" data-uk="АВТО ПІД ЗАМОВЛЕННЯ" '
     'data-ka="ავტომობილი შეკვეთით">АВТО ПІД ЗАМОВЛЕННЯ</span>'),
    ('<br><span data-ru="под ключ в Киеве" data-uk="під ключ у Києві" '
     'data-ka="სრული მომსახურებით კიევში">під ключ у Києві</span></h1>',
     '<br><span data-ru="под ключ" data-uk="під ключ" data-ka="სრული მომსახურებით">під ключ</span></h1>'),
)
# Public proof that the new heading is live.
CHECK = '>під ключ</span></h1>'


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1:
            raise ValueError('HOME_LABEL_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
