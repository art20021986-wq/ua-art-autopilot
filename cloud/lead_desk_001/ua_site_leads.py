"""Site enquiries in the CRM bot: «Клиенты» → «Заявки с сайта» (ADS-READY-001; ORDER-PROCESS-001 desk).

The button opens the enquiry desk (ua_lead_desk): the order package's enquiries with status, reply timer,
manager note, transfer to «Клиенты» and reminders; «В меню» returns to «Клиенты». Active staff with the owner,
administrator or manager role may open it and get the reminders. The enquiries stay in the order package; the
desk keeps its own state in crm.db. The order package's own CRM adapter stays registered as before, so any
earlier «orders:» button keeps working. Without the order package the button is not shown.
"""
import time

CALLBACK = 'leads:list'
BUTTON = 'Заявки с сайта'
BACK = 'cards_clients'


def _runtime():
    from ua_order import host
    loaded = host.current()
    return None if loaded is None or loaded is host.UNAVAILABLE else loaded


def available():
    return _runtime() is not None


def _roles():
    import db
    return (db.ROLE_OWNER, db.ROLE_ADMIN, db.ROLE_MANAGER)


def allowed(update):
    import db
    user = update.effective_user
    staff = db.get_staff(user.id) if user else None
    return bool(staff and staff['active'] and staff['role'] in _roles())


def staff_ids():
    import db
    return sorted({uid for role in _roles() for uid in db.staff_ids_by_role(role)})


def register(app):
    loaded = _runtime()
    if loaded is None:
        return None
    import db
    from ua_lead_desk import Desk
    from ua_lead_desk_store import Store
    from ua_order.bindings import first_group
    from ua_order.telegram import CRMAdapter
    adapter = CRMAdapter(loaded.service.repository, loaded.service.catalog, authorize=allowed, menu_callback=BACK)
    adapter.register(app, group=first_group(app))
    store = Store(db.connect)
    store.initialize()
    desk = Desk(loaded.service.repository, loaded.service.catalog, store, authorize=allowed, staff_ids=staff_ids,
                menu_callback=BACK, clock=time.time)
    desk.register(app, group=first_group(app))
    return desk
