"""Two buttons at the end of the CRM bot main menu (ORDER-PROCESS-001, owner «Да» 2026-11-05).

«📨 Заявки с сайта» opens the enquiry desk directly; «⋯ Ещё» opens the existing hidden screen (Клиенты,
Сотрудники, Сводка, Поиск), which had no way in from the main menu. Pure: takes the menu markup the earlier
hooks built and returns it with the missing rows appended; a row already present is not added twice.
"""
MORE = ('⋯ Ещё', 'crm_more')


def rows_to_add(present, leads_callback):
    rows = []
    if leads_callback and leads_callback not in present:
        rows.append(('📨 Заявки с сайта', leads_callback))
    if MORE[1] not in present:
        rows.append(MORE)
    return rows


def _leads_callback():
    try:
        import ua_site_leads
        return ua_site_leads.CALLBACK if ua_site_leads.available() else None
    except Exception:
        return None


def with_buttons(markup):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [list(row) for row in markup.inline_keyboard]
    present = {getattr(b, 'callback_data', None) for row in rows for b in row}
    rows += [[InlineKeyboardButton(label, callback_data=data)] for label, data in rows_to_add(present, _leads_callback())]
    return InlineKeyboardMarkup(rows)
