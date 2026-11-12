"""lead_bot.py (the client bot): every owner from ua_owners is an admin and gets every notification.

The configured MANAGER_CHAT_ID stays the first owner; owners() adds every active CRM «Владелец». Admin checks, the
owner command menus and all sends to the manager chat use owners(), each owner separately; the screens, the order
inbox and the lead desk get the same owners function. Nothing else changes.
"""
NAME = 'lead_bot.py'
EDITS = (
    ('ADMIN_IDS = [int(MANAGER_CHAT_ID)] if str(MANAGER_CHAT_ID).lstrip("-").isdigit() else []\n',
     'import ua_owners  # STAFF-FULL-ACCESS-001: this chat + every active CRM «Владелец»\n'
     '\n'
     '\n'
     'def owners():\n'
     '    return ua_owners.ids(MANAGER_CHAT_ID)\n'),
    ('    return user_id in ADMIN_IDS\n',
     '    return user_id in owners()\n'),
    # send_to_manager: each owner separately; the lead counts as delivered when at least one owner got it.
    ('    try:\n'
     '        await context.bot.send_message(\n'
     '            chat_id=MANAGER_CHAT_ID,\n'
     '            text=text,\n'
     '            parse_mode="HTML",\n'
     '            reply_markup=taken_markup(lead_id) if lead_id else None,\n'
     '        )\n'
     '        if lead_id:\n'
     '            mark_lead_delivered(lead_id)\n'
     '        return True\n'
     '    except Exception as e:\n'
     '        logging.error(f"НЕ ОТПРАВЛЕНО МЕНЕДЖЕРУ (lead_id={lead_id}): {e}")\n'
     '        return False\n',
     '    sent = False\n'
     '    for chat_id in owners():\n'
     '        try:\n'
     '            await context.bot.send_message(\n'
     '                chat_id=chat_id,\n'
     '                text=text,\n'
     '                parse_mode="HTML",\n'
     '                reply_markup=taken_markup(lead_id) if lead_id else None,\n'
     '            )\n'
     '            sent = True\n'
     '        except Exception as e:\n'
     '            logging.error(f"НЕ ОТПРАВЛЕНО МЕНЕДЖЕРУ (lead_id={lead_id}): {e}")\n'
     '    if sent and lead_id:\n'
     '        mark_lead_delivered(lead_id)\n'
     '    return sent\n'),
    # The reminder about an unanswered lead: to each owner; marked reminded when at least one owner got it.
    ('        try:\n            await context.bot.send_message(\n                chat_id=MANAGER_CHAT_ID,\n                text=(\n                    f"⏰ <b>Заявка #{l.get(\'id\')} висит без ответа {mins} мин.</b>\\n\\n"\n                    f"{who}{phone}\\n"\n                    f"{detail}\\n\\n"\n                    f"<a href=\\"tg://user?id={l.get(\'user_id\')}\\">Написать клиенту</a>"\n                ),\n                parse_mode="HTML",\n                reply_markup=taken_markup(l.get("id")),\n            )\n            mark_lead_reminded(l.get("id"))\n        except Exception as e:\n            logging.warning(f"Не удалось напомнить по лиду {l.get(\'id\')}: {e}")\n',
     '        reminded = False\n        for chat_id in owners():\n            try:\n                await context.bot.send_message(\n                    chat_id=chat_id,\n                    text=(\n                        f"⏰ <b>Заявка #{l.get(\'id\')} висит без ответа {mins} мин.</b>\\n\\n"\n                        f"{who}{phone}\\n"\n                        f"{detail}\\n\\n"\n                        f"<a href=\\"tg://user?id={l.get(\'user_id\')}\\">Написать клиенту</a>"\n                    ),\n                    parse_mode="HTML",\n                    reply_markup=taken_markup(l.get("id")),\n                )\n                reminded = True\n            except Exception as e:\n                logging.warning(f"Не удалось напомнить по лиду {l.get(\'id\')}: {e}")\n        if reminded:\n            mark_lead_reminded(l.get("id"))\n'),
    ('        try:\n'
     '            await context.bot.forward_message(\n'
     '                chat_id=MANAGER_CHAT_ID,\n'
     '                from_chat_id=update.effective_chat.id,\n'
     '                message_id=update.message.message_id,\n'
     '            )\n'
     '        except Exception as e:\n'
     '            logging.warning(f"Не удалось переслать медиа менеджеру: {e}")\n',
     '        for chat_id in owners():\n'
     '            try:\n'
     '                await context.bot.forward_message(\n'
     '                    chat_id=chat_id,\n'
     '                    from_chat_id=update.effective_chat.id,\n'
     '                    message_id=update.message.message_id,\n'
     '                )\n'
     '            except Exception as e:\n'
     '                logging.warning(f"Не удалось переслать медиа менеджеру: {e}")\n'),
    ('    try:\n'
     '        await context.bot.send_message(\n'
     '            chat_id=MANAGER_CHAT_ID,\n'
     '            text=f"⚠️ <b>Ошибка в боте</b>\\n\\n<code>{tb[-1200:]}</code>",\n'
     '            parse_mode="HTML",\n'
     '        )\n'
     '    except Exception:\n'
     '        pass\n',
     '    for chat_id in owners():\n'
     '        try:\n'
     '            await context.bot.send_message(\n'
     '                chat_id=chat_id,\n'
     '                text=f"⚠️ <b>Ошибка в боте</b>\\n\\n<code>{tb[-1200:]}</code>",\n'
     '                parse_mode="HTML",\n'
     '            )\n'
     '        except Exception:\n'
     '            pass\n'),
    ('    # У администратора своё меню — клиенты этих команд не видят\n'
     '    for admin_id in ADMIN_IDS:\n',
     '    # У администратора своё меню — клиенты этих команд не видят\n'
     '    for admin_id in owners():\n'),
    ('        for admin_id in ADMIN_IDS:\n'
     '            await application.bot.set_my_commands(\n'
     '                vladelcu, scope=BotCommandScopeChat(chat_id=admin_id))\n',
     '        for admin_id in owners():\n'
     '            await application.bot.set_my_commands(\n'
     '                vladelcu, scope=BotCommandScopeChat(chat_id=admin_id))\n'),
    ("        _vitrina.register(app, globals().get('MANAGER_CHAT_ID'))\n",
     '        _vitrina.register(app, owners)\n'),
    ('    _register_orders(app, owner_id=MANAGER_CHAT_ID)\n',
     '    _register_orders(app, owners=owners)\n'),
    ('        ua_lead_desk.register(app, owner_id=MANAGER_CHAT_ID)\n',
     '        ua_lead_desk.register(app, owners=owners)\n'),
)
