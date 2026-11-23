"""The CRM bot's edit message inside the UA-0005 card text (SEO-FIX-20261121, owner «Да», 2026-11-21).

When an editor changes condition_text the bot answers «Описание / Сейчас: <current text> / Чтобы изменить — пришлите
новый текст. … / Пришлите новое значение текстом или голосом.»; that whole message was sent back as the text and its
service parts are shown to visitors on every version of the card. Only those parts are removed: the «Описание»
first line, the «Сейчас: » prefix of the next line, the two instruction lines, and the blank lines this leaves
doubled at the end. Every other line, field and row stays as it is.
"""
import json

NUMBER = 'UA-0005'
HINT = 'Чтобы изменить — пришлите новый текст. Он полностью заменит нынешний. Каждый пункт с новой строки.'
PROMPT = 'Пришлите новое значение текстом или голосом.'
LABEL = 'Описание'
NOW = 'Сейчас: '
# Visible on the published card, each line as its own item: Russian on the base and ru/ pages, Ukrainian on ua/.
RU_MARKS = ('<div>Описание</div>', 'Сейчас: 🚘', 'Чтобы изменить — пришлите новый текст', 'Пришлите новое значение текстом')
UK_MARKS = ('<div>Опис</div>', 'Зараз: 🚘', 'Щоб змінити — надішліть новий текст', 'Надішліть нове значення текстом')
MARKS = {'': RU_MARKS, 'ru/': RU_MARKS, 'ua/': UK_MARKS}
IDENTITY = ('id', 'auto_number', 'vin')


def without_hint(value):
    """The text without the bot message parts; unchanged when the text does not carry the hint line."""
    lines = value.split('\n')
    if not any(line.strip() == HINT for line in lines):
        return value
    kept = [line for line in lines if line.strip() not in (HINT, PROMPT)]
    if len(kept) > 1 and kept[0].strip() == LABEL and kept[1].startswith(NOW):
        kept = [kept[1][len(NOW):]] + kept[2:]
    return '\n'.join(kept).rstrip('\n')


def card(rows):
    found = [row for row in rows if str(row.get('auto_number') or '') == NUMBER]
    if len(found) != 1:
        raise ValueError('CARD_IDENTITY:%d' % len(found))
    return found[0]


def plan_for(rows):
    row = card(rows)
    changes = [{'id': row['id'], 'auto_number': NUMBER, 'vin': str(row['vin'] or '').strip().upper(), 'field': field,
                'before': value, 'after': without_hint(value)}
               for field, value in sorted(row.items())
               if field not in IDENTITY and isinstance(value, str) and without_hint(value) != value]
    # The hint inside a line with other text is reported, never edited.
    inline = sorted(f for f, v in row.items() if isinstance(v, str) and HINT in v and without_hint(v) == v)
    if not changes or inline:
        raise ValueError('HINT_NOT_ALONE' if inline else 'HINT_ABSENT')
    return {'changes': changes}


def allowed(item):
    """The only edit this package may write: the hint line removed from a UA-0005 text field."""
    before = item['before']
    return (item['auto_number'] == NUMBER and item['field'] not in IDENTITY and isinstance(before, str)
            and HINT in before and item['after'] == without_hint(before)
            and not any(text in item['after'] for text in (HINT, PROMPT, NOW)))


# The site script translates every card line by its dictionaries; the card language versions are built only when
# each line has Ukrainian. The «Сейчас: <line>» entry exists, the bare <line> does not: it is added to the Ukrainian
# and Georgian dictionaries with the same translation minus the «Зараз: » / «ახლა: » prefix. Nothing else changes.
SCRIPT = 'video/ua-site-languages.js'
DICTIONARIES = 'var dictionaries = '
PREFIXES = {'uk': 'Зараз: ', 'ka': 'ახლა: '}


def dictionaries(script):
    start = script.index(DICTIONARIES) + len(DICTIONARIES)
    return json.JSONDecoder().raw_decode(script[start:])[0]


def new_line(change):
    """The first line the text starts with after the fix, when it came from a «Сейчас: » line; else None."""
    lines = change['before'].split('\n')
    if len(lines) > 1 and lines[0].strip() == LABEL and lines[1].startswith(NOW):
        return lines[1][len(NOW):]
    return None


def script_edit(script, line):
    """The script with «line» added to the uk and ka dictionaries next to the «Сейчас: line» entry (idempotent)."""
    before = dictionaries(script)
    wanted = {lang: dict(words) for lang, words in before.items()}
    edited = script
    for lang, prefix in PREFIXES.items():
        old_value = before[lang].get(NOW + line)
        if old_value is None or not old_value.startswith(prefix):
            raise ValueError('SCRIPT_ENTRY_MISSING:' + lang)
        value = old_value[len(prefix):]
        wanted[lang][line] = value
        if before[lang].get(line) == value:
            continue
        if line in before[lang]:
            raise ValueError('SCRIPT_ENTRY_DIFFERS:' + lang)
        entry = json.dumps(NOW + line, ensure_ascii=False) + ':' + json.dumps(old_value, ensure_ascii=False)
        if edited.count(entry) != 1:
            raise ValueError('SCRIPT_ENTRY_NOT_UNIQUE:' + lang)
        added = ',' + json.dumps(line, ensure_ascii=False) + ':' + json.dumps(value, ensure_ascii=False)
        edited = edited.replace(entry, entry + added)
    if dictionaries(edited) != wanted:
        raise ValueError('SCRIPT_DICTIONARY_DRIFT')
    return edited
