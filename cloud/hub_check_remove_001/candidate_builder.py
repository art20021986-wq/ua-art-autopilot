"""Build the HUB-CHECK-REMOVE-001 candidate (owner 2026-11-13: «Убери этот раздел... Удали немедленно»).

The «Авто з Кореї» hubs (uk and ru) lose the section «Як ми перевіряємо авто до покупки» / «Как мы проверяем авто
до покупки»: its texts and its place in ua_seo_hub_texts.hub are removed entirely, so no landing build brings it
back; the install's landing refresh rewrites the two hubs. Every other text and byte stays as it is.
"""
NAME = 'ua_seo_hub_texts.py'
MARK = 'HUB-CHECK-REMOVE-001'
EDITS = {NAME: [
    ("        check_title='Як ми перевіряємо авто до покупки',\n"
     "        check=('Дивимося звіт аукціону: оцінка кузова, салону й технічного стану.',\n"
     "               \"За потреби перевіряємо лакофарбове покриття, робимо комп'ютерну діагностику й технічний огляд.\"),\n", ''),
    ("        check_title='Как мы проверяем авто до покупки',\n"
     "        check=('Смотрим отчёт аукциона: оценка кузова, салона и технического состояния.',\n"
     "               'При необходимости проверяем лакокрасочное покрытие, делаем компьютерную диагностику и технический осмотр.'),\n", ''),
    ('    """«Why UA ART», «most ordered models» (linked) and «how we check» for the Korea hub."""\n',
     '    """«Why UA ART» and «most ordered models» (linked) for the Korea hub (HUB-CHECK-REMOVE-001)."""\n'),
    ("    return (_list(t['why_title'], [escape(x) for x in t['why']]) + _list(t['models_title'], models)\n"
     "            + _list(t['check_title'], [escape(x) for x in t['check']]) + _ukraine(lang, link))\n",
     "    return (_list(t['why_title'], [escape(x) for x in t['why']]) + _list(t['models_title'], models)\n"
     "            + _ukraine(lang, link))\n"),
]}
DEPENDENCY_SHA256 = {}


def targets(root):
    return tuple(EDITS)


def build(source, dependencies, read_original=None):
    text = source[NAME].decode('utf-8')
    if MARK in text:
        raise ValueError('HUB_CHECK_ALREADY_APPLIED')
    for old, new in EDITS[NAME]:
        if text.count(old) != 1:
            raise ValueError('HUB_CHECK_EDIT:%d:%s' % (text.count(old), old[:40]))
        text = text.replace(old, new)
    if 'check' in text.replace('checked', ''):
        raise ValueError('HUB_CHECK_LEFT')
    return {NAME: text.encode('utf-8')}
