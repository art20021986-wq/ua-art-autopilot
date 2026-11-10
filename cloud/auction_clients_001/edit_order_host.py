"""ua_order/host.py: the site application also answers /api/auction/* (client login, module ua_auction_web).

The site's WSGI file already calls ua_order.host.mount_application; the auction login is put in front there, isolated:
if it cannot load, the order endpoints and the site work as before. Fragment edit; the original must occur once.
"""
PATH = 'ua_order/host.py'

EDITS = (
    ("def mount_application(application):\n    loaded = current()\n",
     "def mount_application(application):\n"
     "    try:  # JPAUTO-KOREA-001: auction client login (/api/auction/*), independent of the order feature\n"
     "        import ua_auction_web\n"
     "        application = ua_auction_web.mount(application)\n"
     "    except Exception as exc:\n"
     "        log.error('Auction login unavailable (%s)', type(exc).__name__)\n"
     "    loaded = current()\n"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('ORDER_HOST_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
