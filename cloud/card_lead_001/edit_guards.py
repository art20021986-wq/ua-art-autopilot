"""Card publication checks (ua_additional_spec.py, publikaciya.py): the expected primary action is the one
«Связаться с менеджером» button from ua_card_contact (LEAD-FOLDERS-001). Only the expected label changes; every
other rule of the checks stays. Each original fragment must occur exactly once and an applied fragment is refused.
"""
EDITS = {
    'ua_additional_spec.py': (
        ('def _expected_action(uid: str) -> str:\n'
         '    return "Купить" if _stage_number(uid) == 4 else "Задаток 500 $"\n',
         'def _expected_action(uid: str) -> str:\n'
         '    import ua_card_contact  # LEAD-FOLDERS-001: one «Связаться с менеджером» button\n'
         "    return ua_card_contact.LABEL['ru']\n"),
    ),
    'publikaciya.py': (
        ('    expected = "Купить" if stage == 4 else "Задаток 500 $"\n',
         '    import ua_card_contact  # LEAD-FOLDERS-001: one «Связаться с менеджером» button\n'
         "    expected = ua_card_contact.LABEL['ru']\n"),
    ),
}


def build(name, source):
    text = source.decode('utf-8')
    for old, new in EDITS[name]:
        if text.count(old) != 1 or new in text:
            raise ValueError('GUARD_FRAGMENT_NOT_UNIQUE:' + name)
        text = text.replace(old, new)
    return text.encode('utf-8')
