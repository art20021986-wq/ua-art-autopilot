"""Owner-approved buttons in the CRM bot main menu (ORDER-PROCESS-001, owner 2026-11-05: «сотрудники в CRM,
клиенты в CRM»): «👤 Клиенты» (site enquiries live inside it) and «👥 Сотрудники».

The bot builds the full menu for the person's role (team_bot.main_menu: «Клиенты» for staff, «Сотрудники» for the
owner only); an earlier hook hides both. This puts back exactly those two buttons from the role's own menu, with
their own labels, so nobody gets a button their role does not have. Nothing else is added.
"""
RESTORED = ('cards_clients', 'staff_list')


def with_buttons(full, menu):
    """full: the role's menu before hiding; menu: what the earlier hooks show. Returns menu plus the two buttons."""
    from telegram import InlineKeyboardMarkup
    rows = [list(row) for row in menu.inline_keyboard]
    present = {getattr(b, 'callback_data', None) for row in rows for b in row}
    for data in RESTORED:
        if data in present:
            continue
        button = next((b for row in full.inline_keyboard for b in row if getattr(b, 'callback_data', None) == data), None)
        if button is not None:
            rows.append([button])
    return InlineKeyboardMarkup(rows)
