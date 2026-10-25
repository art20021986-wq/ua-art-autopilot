"""Order page: the other-model button becomes a gold «choose another car» button (PODBOR-OTHER-001).

Owner request 2026-10-25. The button gets its own label key, so the selection line that
still says «other model» is not affected. The strings file is fetched with the module's
version query and that version is raised, so browsers do not mix a cached old strings
file with the new page. Each original fragment must occur exactly once, otherwise
nothing is changed;
an already applied fragment is refused too.
"""

PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'

EDITS = {
    PAGE: (
        ('<button type="button" id="other-model" class="secondary" data-label="other">Інша модель</button>',
         '<button type="button" id="other-model" data-label="other_choose">Обрати інший автомобіль</button>'),
        ('<script type="module" src="order/order.js?v=20260927.10">',
         '<script type="module" src="order/order.js?v=20261025.1">'),
    ),
    SCRIPT: (
        ("fetch(new URL('order-strings.json',assets))",
         "fetch(new URL('order-strings.json'+new URL(import.meta.url).search,assets))"),
    ),
    STRINGS: (
        ('    "other": "Інша модель",\n',
         '    "other": "Інша модель",\n    "other_choose": "Обрати інший автомобіль",\n'),
        ('    "other": "Другая модель",\n',
         '    "other": "Другая модель",\n    "other_choose": "Выбрать другой автомобиль",\n'),
        ('    "other": "სხვა მოდელი",\n',
         '    "other": "სხვა მოდელი",\n    "other_choose": "სხვა ავტომობილის არჩევა",\n'),
    ),
}
# Public proof that each file is live.
CHECK_PAGE = 'data-label="other_choose"'
CHECK_SCRIPT = "new URL(import.meta.url).search"
CHECK_STRINGS = '"other_choose": "Обрати інший автомобіль"'


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
