"""Who has the owner's full rights in the bots (STAFF-FULL-ACCESS-001, owner 2026-11-24).

«👑 Владелец» and «🛡 Управляющий администратор» see and may do the same and get the same notifications; each keeps
the role name. Every owner-only check and owner notification asks this module, so the rule lives in one place.
"""
import logging


def roles():
    """The roles with full rights."""
    import db
    return (db.ROLE_OWNER, db.ROLE_ADMIN)


def ids(primary=None):
    """Chat ids with full rights: `primary` (a configured owner chat, int or digit string) first, then the active
    owners and managing administrators of the CRM staff. If the CRM cannot be read, `primary` alone, as before."""
    result = []
    try:
        first = int(str(primary).strip())
    except (TypeError, ValueError):
        first = 0
    if first > 0:
        result.append(first)
    try:
        import db
        for role in roles():
            result += [int(i) for i in db.staff_ids_by_role(role) if int(i) not in result]
    except Exception as error:
        logging.error('ua_full_access: CRM staff not read: %s', error)
    return result
