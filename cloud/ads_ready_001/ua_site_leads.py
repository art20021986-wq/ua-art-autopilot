"""Site enquiries in the CRM bot: «Клиенты» → «Заявки с сайта» (ADS-READY-001, owner request 2026-10-30).

The order package's own inbox (ua_order CRMAdapter: the list and each enquiry with its ad source) is
registered in the CRM bot as it already is in the client bot; «В меню» returns to «Клиенты». Active staff
with the owner, administrator or manager role may open it. The enquiries stay in the order package;
the CRM database is only read for the staff role. Without the order package the button is not shown.
"""
CALLBACK = 'orders:list'
BUTTON = 'Заявки с сайта'
BACK = 'cards_clients'


def _runtime():
    from ua_order import host
    loaded = host.current()
    return None if loaded is None or loaded is host.UNAVAILABLE else loaded


def available():
    return _runtime() is not None


def allowed(update):
    import db
    user = update.effective_user
    staff = db.get_staff(user.id) if user else None
    return bool(staff and staff['active'] and staff['role'] in (db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER))


def register(app):
    loaded = _runtime()
    if loaded is None:
        return None
    from ua_order.bindings import first_group
    from ua_order.telegram import CRMAdapter
    adapter = CRMAdapter(loaded.service.repository, loaded.service.catalog, authorize=allowed, menu_callback=BACK)
    adapter.register(app, group=first_group(app))
    return adapter
