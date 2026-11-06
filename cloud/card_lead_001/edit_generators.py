"""Card generators (stranica.py, master_card.py): the stage primary action becomes the one «Связаться с менеджером»
button from ua_card_contact (LEAD-FOLDERS-001). Both files carry the same primary-action step; only its label,
markup, page finish and check change — the stage, the bot address and every other rule stay. Each original
fragment must occur exactly once and an applied fragment is refused.
"""
NAMES = ('stranica.py', 'master_card.py')
IMPORT = '    import ua_card_contact as _ua_card_contact  # LEAD-FOLDERS-001: one «Связаться с менеджером» button\n'
EDITS = (
    ('\n    label = "Купить" if stage == 4 else "Задаток 500 $"\n',
     '\n' + IMPORT + "    label = _ua_card_contact.LABEL['ru']\n"),
    ("    canonical = ('<a class=\"dejstvie kn_kupit ua-primary-action-v1\" '\n"
     "                 'data-ua-stage-action=\"%d\" href=\"%s\">%s</a>'\n"
     "                 % (stage, _ua068_e(href), label))\n",
     '    canonical = _ua_card_contact.button(stage, href, str(kod))\n'),
    ('    return source\n\n\ndef _ua068_primary_action_errors(',
     '    return _ua_card_contact.finish(source)\n\n\ndef _ua068_primary_action_errors('),
    ('    expected_label = "Купить" if stage == 4 else "Задаток 500 $"\n',
     IMPORT + "    expected_label = _ua_card_contact.LABEL['ru']\n"),
    ('    if text != expected_label:\n        errors.append("primary action label mismatch")\n    return errors\n',
     '    if text != expected_label:\n        errors.append("primary action label mismatch")\n'
     '    errors.extend(_ua_card_contact.errors(source))\n    return errors\n'),
)


def build(name, source):
    if name not in NAMES:
        raise ValueError('GENERATOR_NAME:' + name)
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('GENERATOR_FRAGMENT_NOT_UNIQUE:%s:%s' % (name, old.strip()[:40]))
        text = text.replace(old, new)
    return text.encode('utf-8')
