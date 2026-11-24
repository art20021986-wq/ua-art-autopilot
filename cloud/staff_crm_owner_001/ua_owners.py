"""Who the client bot's owners are (STAFF-FULL-ACCESS-001, owner 2026-11-12).

One answer for every screen, command and notification of the client bot: the configured owner chat first, then every
active «👑 Владелец» of the CRM staff. The owner gives a person that role in the CRM bot and the client bot treats the
person exactly as the owner. If the CRM cannot be read, the configured chat alone stays the owner, as before.
"""
import logging


def ids(primary):
    """Owner chat ids: `primary` (the configured chat, int or digit string) first, then the active CRM owners."""
    result = []
    try:
        first = int(str(primary).strip())
    except (TypeError, ValueError):
        first = 0
    if first > 0:
        result.append(first)
    try:
        import db
        result += [int(i) for i in db.staff_ids_by_role(db.ROLE_OWNER) if int(i) not in result]
    except Exception as error:
        logging.error('ua_owners: CRM owners not read: %s', error)
    return result
