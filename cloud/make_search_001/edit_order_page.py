"""Order page and script: load the searchable list (search-picker.css) and the new form module versions.

podbor.html links the list styles next to the other order styles and raises the order script version; order.js asks
for the new preferences-form.js version, so browsers do not keep the old module. Each original fragment must occur
exactly once and an applied fragment is refused.
"""
PAGE = 'video/podbor.html'
SCRIPT = 'video/order/order.js'
EDITS = {
    PAGE: (
        ('order/order.js?v=20261105.1', 'order/order.js?v=20261106.1'),
        ('<link rel="stylesheet" href="order/quick-lead.css?v=20261030.1">',
         '<link rel="stylesheet" href="order/quick-lead.css?v=20261030.1">'
         '<link rel="stylesheet" href="order/search-picker.css?v=20261106.1">'),
    ),
    SCRIPT: (
        ("import {PreferenceForm} from './preferences-form.js?v=20260927.10';",
         "import {PreferenceForm} from './preferences-form.js?v=20261106.1';"),
    ),
}
# Public proof that each file is live.
CHECK_PAGE = 'order/search-picker.css?v=20261106.1'
CHECK_SCRIPT = "./preferences-form.js?v=20261106.1'"


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
