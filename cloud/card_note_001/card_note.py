"""The CRM bot's edit hint inside the UA-0005 card text (SEO-FIX-20261121, owner «Да», 2026-11-21).

The bot shows «Чтобы изменить — пришлите новый текст. …» under the current card text when an editor changes
condition_text; the hint was sent back as part of the text and is shown to visitors on every version of the card.
Only that line is removed; the card is identified by its number and its VIN (read at the preview); every other
line, field and row stays as it is.
"""
NUMBER = 'UA-0005'
HINT = 'Чтобы изменить — пришлите новый текст. Он полностью заменит нынешний. Каждый пункт с новой строки.'
# Visible on the published card: the Russian line (base and ru/) and its Ukrainian translation (ua/).
MARKS = {'': 'Чтобы изменить — пришлите новый текст', 'ru/': 'Чтобы изменить — пришлите новый текст',
         'ua/': 'Щоб змінити — надішліть новий текст'}
IDENTITY = ('id', 'auto_number', 'vin')


def without_hint(value):
    """The text without the hint lines (exact line match, surrounding blanks ignored)."""
    lines = value.split('\n')
    kept = [line for line in lines if line.strip() != HINT]
    return '\n'.join(kept).rstrip('\n') if len(kept) != len(lines) else value


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
            and HINT in before and item['after'] == without_hint(before) and HINT not in item['after'])
