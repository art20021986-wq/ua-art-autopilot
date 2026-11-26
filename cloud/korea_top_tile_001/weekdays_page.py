"""Korea page: the auction days are Monday to Friday (KOREA-TOP-TILE-001, owner 2026-11-26 «3 — да»).

The page said «Торги щодня з понеділка по суботу» and «Щодня з понеділка по суботу.»; the auction lists showed no
Saturday auction in three weeks (12-26.11) and an AutoPlus auction every Friday. Two exact replacements (uk/ru/ka);
every other byte of video/korea.html stays; each edit must match exactly once.
"""
EDITS = (
    ('<span data-uk="Торги щодня з понеділка по суботу" data-ru="Торги каждый день с понедельника по субботу" '
     'data-ka="ვაჭრობა ყოველდღე ორშაბათიდან შაბათამდე">Торги щодня з понеділка по суботу',
     '<span data-uk="Торги щодня з понеділка по п\'ятницю" data-ru="Торги каждый день с понедельника по пятницу" '
     'data-ka="ვაჭრობა ყოველდღე ორშაბათიდან პარასკევამდე">Торги щодня з понеділка по п\'ятницю'),
    ('<span data-uk="Щодня з понеділка по суботу." data-ru="Ежедневно с понедельника по субботу.">'
     'Щодня з понеділка по суботу.',
     '<span data-uk="Щодня з понеділка по п\'ятницю." data-ru="Ежедневно с понедельника по пятницу.">'
     'Щодня з понеділка по п\'ятницю.'),
)


def build(source):
    text = source.decode('utf-8')
    if any(text.count(old) != 1 for old, _ in EDITS):
        raise ValueError('WEEKDAYS_ANCHOR')
    for old, new in EDITS:
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
