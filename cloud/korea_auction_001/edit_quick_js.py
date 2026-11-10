"""video/order/quick-lead.js: the shared manager dialog also opens from [data-quick-lead-auction]
(the «Korea online auctions» page) and then sends ua_order_request.auction.v1.

Fragment edits of the live script; each original fragment must occur exactly once, an applied edit is refused.
"""
PATH = 'video/order/quick-lead.js'

EDITS = (
    ("event.target.closest('[data-quick-lead-model],[data-quick-lead-car]')",
     "event.target.closest('[data-quick-lead-model],[data-quick-lead-car],[data-quick-lead-auction]')"),
    ("        if (opener.dataset.quickLeadCar) {\n",
     "        delete form.dataset.auction;\n"
     "        if (opener.dataset.quickLeadAuction) {\n"
     "          delete form.dataset.car; form.dataset.auction = opener.dataset.quickLeadAuction;\n"
     "        } else if (opener.dataset.quickLeadCar) {\n"),
    ("      if (car) { payload.car_code = car; } else {",
     "      if (form.dataset.auction) {\n"
     "        payload.schema_version = 'ua_order_request.auction.v1';\n"
     "        payload.purchase_country_code = form.dataset.auction;\n"
     "      } else if (car) { payload.car_code = car; } else {"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('QUICK_JS_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
