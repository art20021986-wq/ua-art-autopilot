"""Edits of installed bots for the lead desk and orders (LEAD-FOLDERS-001). Each original fragment must occur
exactly once and an applied fragment is refused.

cars_ui.py (CRM bot): «👤 Клиенты» shows orders by folder (ua_crm_orders) instead of the client list, «Заявки с сайта»
and «Заявки из бота» (leads now live in the client bot); the order buttons are registered instead of ua_site_leads.
lead_bot.py (client bot): the lead desk (ua_lead_desk) is registered after the order package.
ua_order/bindings.py: the owner's new-enquiry message opens the lead card of the desk.
"""
OLD_CLIENTS_SCREEN = 'async def clients_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    """Раздел «Клиенты»: сами клиенты, поиск и заявки из бота."""\n    q = update.callback_query\n    await _v168_ack(q,)\n    try:\n        spisok = db.list_cards("clients", limit=20)\n    except Exception as e:\n        log.warning("Клиенты: %s", e)\n        spisok = []\n\n    lines = ["<b>Клиенты</b>"]\n    rows = []\n    if spisok:\n        for k in spisok:\n            imya = k.get("name") or "без имени"\n            tel = k.get("phone") or ""\n            podpis = "%s%s" % (imya, " · " + tel if tel else "")\n            rows.append([InlineKeyboardButton(podpis[:40],\n                                              callback_data="card_open:clients:%d" % k["id"])])\n    else:\n        lines.append("Пока пусто. Клиент появится, когда оформите машину за покупателем.")\n\n    rows.append([InlineKeyboardButton("Поиск клиента", callback_data="search_start")])\n    # ADS-READY-001: site enquiries (module ua_site_leads).\n    try:\n        import ua_site_leads\n        if ua_site_leads.available():\n            rows.append([InlineKeyboardButton(ua_site_leads.BUTTON, callback_data=ua_site_leads.CALLBACK)])\n    except Exception as e:\n        log.warning("ua_site_leads: кнопка не добавлена: %s", e)\n    # FINANCE-001: visits to the finance partners (module ua_finance_crm).\n    try:\n        import ua_finance_crm\n        rows.append([InlineKeyboardButton(ua_finance_crm.BUTTON, callback_data=ua_finance_crm.CALLBACK)])\n    except Exception as e:\n        log.warning("ua_finance_crm: кнопка не добавлена: %s", e)\n    rows.append([InlineKeyboardButton("Заявки из бота", callback_data="crm_leads")])\n    rows.append([InlineKeyboardButton("← Назад", callback_data="menu")])\n    await q.message.reply_text("\\n".join(lines), parse_mode="HTML",\n                               reply_markup=InlineKeyboardMarkup(rows))\n    raise ApplicationHandlerStop\n\n\n'
NEW_CLIENTS_SCREEN = (
    'async def clients_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):\n'
    '    """Раздел «Клиенты»: заказы по договорам, папки по источнику (LEAD-FOLDERS-001, модуль ua_crm_orders)."""\n'
    '    import ua_crm_orders\n'
    '    await ua_crm_orders.clients_screen(update, context)\n'
    '\n'
    '\n')
EDITS = {
    'cars_ui.py': (
        (OLD_CLIENTS_SCREEN, NEW_CLIENTS_SCREEN),
        ("# ADS-READY-001: «Заявки с сайта» in «Клиенты» (module ua_site_leads).\n"
         "_ua_site_leads_register = register\n"
         "\n"
         "\n"
         "def register(app):\n"
         "    _ua_site_leads_register(app)\n"
         "    try:\n"
         "        import ua_site_leads\n"
         "        ua_site_leads.register(app)\n"
         "    except Exception as e:\n"
         "        log.warning('ua_site_leads не подключён: %s', e)\n",
         "# LEAD-FOLDERS-001: orders by folder in «Клиенты» (module ua_crm_orders).\n"
         "_ua_crm_orders_register = register\n"
         "\n"
         "\n"
         "def register(app):\n"
         "    _ua_crm_orders_register(app)\n"
         "    try:\n"
         "        import ua_crm_orders\n"
         "        ua_crm_orders.register(app)\n"
         "    except Exception as e:\n"
         "        log.warning('ua_crm_orders не подключён: %s', e)\n"),
    ),
    'lead_bot.py': (
        ("    _register_orders(app, owner_id=MANAGER_CHAT_ID)\n",
         "    _register_orders(app, owner_id=MANAGER_CHAT_ID)\n"
         "    # LEAD-FOLDERS-001: the lead desk (leads by folder, «Оформить договор»)\n"
         "    try:\n"
         "        import ua_lead_desk\n"
         "        ua_lead_desk.register(app, owner_id=MANAGER_CHAT_ID)\n"
         "    except Exception as e:\n"
         "        logging.error('ua_lead_desk не подключён: %s', e)\n"),
    ),
    'ua_order/bindings.py': (
        ("reply_markup=_markup([[('Открыть заявку', f'orders:open:{row[\"id\"]}')]])",
         "reply_markup=_markup([[('Открыть лид', f'ld:o:or:{row[\"id\"]}')]])"),
    ),
}


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('BOT_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
