"""First-screen and step-5 texts of the home page: Ukraine and Georgia instead of Kyiv (HOME-TEXT-001).

Owner-approved wording 2026-10-25 (variant A). Only these four labels change; every
other byte stays as is. Each original label must occur exactly once, otherwise
nothing is changed.
"""

EDITS = (
    ('<span class="eyebrow" data-ru="АВТО ПОД ЗАКАЗ · КИЕВ" data-uk="АВТО ПІД ЗАМОВЛЕННЯ · КИЇВ" '
     'data-ka="ავტომობილი შეკვეთით · კიევი">АВТО ПІД ЗАМОВЛЕННЯ · КИЇВ</span>',
     '<span class="eyebrow" data-ru="АВТО ПОД ЗАКАЗ · УКРАИНА И ГРУЗИЯ" data-uk="АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ" '
     'data-ka="ავტომობილი შეკვეთით · საქართველო და უკრაინა">АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ</span>'),
    ('<br><span data-ru="под ключ в Киеве" data-uk="під ключ у Києві" '
     'data-ka="სრული მომსახურებით კიევში">під ключ у Києві</span></h1>',
     '<br><span data-ru="под ключ" data-uk="під ключ" data-ka="სრული მომსახურებით">під ключ</span></h1>'),
    ('<p data-ru="Подберём автомобиль под ваш бюджет и пожелания" data-uk="Підберемо автомобіль під ваш бюджет і побажання" '
     'data-ka="შეგირჩევთ ავტომობილს თქვენი ბიუჯეტისა და სურვილების შესაბამისად">Підберемо автомобіль під ваш бюджет і побажання</p>',
     '<p data-ru="Подберём автомобиль под ваш бюджет и пожелания — для клиентов со всей Украины и Грузии" '
     'data-uk="Підберемо автомобіль під ваш бюджет і побажання — для клієнтів з усієї України та Грузії" '
     'data-ka="შეგირჩევთ ავტომობილს თქვენი ბიუჯეტისა და სურვილების შესაბამისად — კლიენტებისთვის მთელი საქართველოდან და უკრაინიდან">'
     'Підберемо автомобіль під ваш бюджет і побажання — для клієнтів з усієї України та Грузії</p>'),
    ('<small data-ru="В Киеве, с сопровождением" data-uk="У Києві, з супроводом" '
     'data-ka="კიევში, თანხლებით">У Києві, з супроводом</small>',
     '<small data-ru="В Украине и Грузии, с сопровождением" data-uk="В Україні та Грузії, з супроводом" '
     'data-ka="საქართველოსა და უკრაინაში, თანხლებით">В Україні та Грузії, з супроводом</small>'),
)
# Public proof that the new texts are live.
CHECK = '>АВТО ПІД ЗАМОВЛЕННЯ · УКРАЇНА ТА ГРУЗІЯ</span>'


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1:
            raise ValueError('HOME_LABEL_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
