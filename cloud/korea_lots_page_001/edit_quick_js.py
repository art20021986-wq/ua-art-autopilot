"""video/order/quick-lead.js: an opener with [data-quick-lead-lot] (a lot card on the Korea auctions page) adds the
chosen lot to the auction enquiry (ua_order_request.auction.v1, optional field `lot`).

Fragment edits of the live script (as KOREA-AUCTION-INSTALL-20261110-R3 left it); each original fragment must occur
exactly once, an applied edit is refused.
"""
PATH = 'video/order/quick-lead.js'

EDITS = (
    ("          delete form.dataset.car; form.dataset.auction = opener.dataset.quickLeadAuction;\n",
     "          delete form.dataset.car; form.dataset.auction = opener.dataset.quickLeadAuction;\n"
     "          if (opener.dataset.quickLeadLot) {\n"
     "            form.dataset.lot = opener.dataset.quickLeadLot;\n"
     "            form.dataset.lotTitle = opener.dataset.quickLeadLotTitle || '';\n"
     "          } else { delete form.dataset.lot; delete form.dataset.lotTitle; }\n"),
    ("        payload.purchase_country_code = form.dataset.auction;\n",
     "        payload.purchase_country_code = form.dataset.auction;\n"
     "        if (form.dataset.lot) payload.lot = {id: form.dataset.lot, title: form.dataset.lotTitle};\n"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('QUICK_JS_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
