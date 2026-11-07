"""vitrina.py (the client bot's screens, LEAD-FOLDERS-001 fix): the owner's «📁 Авто под заказ» (the old flat list of
the same enquiries) becomes «📥 Лиды», the lead desk by folder; a message the lead desk waits for (a note, the
contract number) goes on to the desk instead of being forwarded as a customer message. Nothing else changes.
Each original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'vitrina.py'
EDITS = (
    ("        from ua_order.crm import FOLDER_LABEL\n"
     "        knopki = list(knopki) + [[(FOLDER_LABEL, 'orders:list')], [('📊 Аналитика', 'v_analytics')]]\n",
     "        import ua_lead_desk  # LEAD-FOLDERS-001: leads by folder\n"
     "        knopki = list(knopki) + [[(ua_lead_desk.BUTTON, ua_lead_desk.CALLBACK)], [('📊 Аналитика', 'v_analytics')]]\n"),
    ('    tekst = (soobshchenie.text or "").strip()\n',
     '    tekst = (soobshchenie.text or "").strip()\n'
     '    # LEAD-FOLDERS-001: a step of the lead desk (note, contract number) waits for this message\n'
     '    try:\n'
     '        import ua_lead_desk\n'
     '        if ua_lead_desk.pending(app, kto):\n'
     '            return False\n'
     '    except Exception as e:\n'
     '        zapis("ua_lead_desk: %s" % e)\n'),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('VITRINA_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
