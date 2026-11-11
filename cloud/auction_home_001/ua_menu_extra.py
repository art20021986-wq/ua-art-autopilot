"""Owner-approved buttons in the CRM bot main menu: «👤 Клиенты» and «👥 Сотрудники» (ORDER-PROCESS-001, owner
2026-11-05) and «🔨 Клиенты аукциона» right under «👤 Клиенты» (JPAUTO-KOREA-001, owner 2026-11-11).

The bot builds the full menu for the person's role (team_bot.main_menu: «Клиенты» for staff, «Сотрудники» for the
owner only); an earlier hook hides both. This puts back exactly those two buttons from the role's own menu, with
their own labels, so nobody gets a button their role does not have; «🔨 Клиенты аукциона» is shown to exactly those
who have «👤 Клиенты» (the auction client screens check the same access). Nothing else is added.
"""
RESTORED = ('cards_clients', 'staff_list')
AUCTION = ('🔨 Клиенты аукциона', 'ac:home')  # ua_auction_clients_view.HOME
AFTER = 'cards_clients'


def with_buttons(full, menu):
    """full: the role's menu before hiding; menu: what the earlier hooks show. Returns menu plus the buttons."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [list(row) for row in menu.inline_keyboard]
    present = {getattr(b, 'callback_data', None) for row in rows for b in row}
    for data in RESTORED:
        if data in present:
            continue
        button = next((b for row in full.inline_keyboard for b in row if getattr(b, 'callback_data', None) == data), None)
        if button is not None:
            rows.append([button])
    datas = [[getattr(b, 'callback_data', None) for b in row] for row in rows]
    at = next((i for i, row in enumerate(datas) if AFTER in row), None)
    if at is not None and not any(AUCTION[1] in row for row in datas):
        rows.insert(at + 1, [InlineKeyboardButton(AUCTION[0], callback_data=AUCTION[1])])
    return InlineKeyboardMarkup(rows)
