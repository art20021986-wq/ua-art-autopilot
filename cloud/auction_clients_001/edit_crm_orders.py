"""ua_crm_orders.py (CRM bot «👤 Клиенты», as LEAD-GROUPS-INSTALL-20261110-R2 installed it): the «🇰🇷 Корея» auction
folder also shows «➕ Создать клиента» and «👥 Клиенты с доступом · N», and the auction client buttons are registered.

Fragment edits; each original fragment must occur exactly once, an applied edit is refused.
"""
PATH = 'ua_crm_orders.py'

EDITS = (
    ("        return view.list_view(parts[2], _book().in_folder(parts[2]))\n",
     "        screen = view.list_view(parts[2], _book().in_folder(parts[2]))\n"
     "        if parts[2] in view.folders.AUCTION_FOLDERS:  # JPAUTO-KOREA-001: clients with online access\n"
     "            import ua_auction_clients_bot\n"
     "            screen['buttons'][-1:-1] = ua_auction_clients_bot.folder_rows()\n"
     "        return screen\n"),
    ("    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)\n    return group\n",
     "    app.add_handler(MessageHandler(filters.COMMAND, cancel), group=group)\n"
     "    try:  # JPAUTO-KOREA-001: «➕ Создать клиента», «👥 Клиенты с доступом» (module ua_auction_clients_bot)\n"
     "        import ua_auction_clients_bot\n"
     "        ua_auction_clients_bot.register(app)\n"
     "    except Exception as exc:\n"
     "        log.warning('ua_auction_clients_bot не подключён: %s', exc)\n"
     "    return group\n"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('CRM_ORDERS_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
