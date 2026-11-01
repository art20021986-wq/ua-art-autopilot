"""Named CRM fields in a voice note: «цена Грузии 17 500, контейнер MSCU1234567, предоплата 1000».

Pure text in, commands out. A field is changed only when its name is said; its value is the
text up to the next field name. Covers the card fields that the free-speech parser does not
read and the buyer's fields; those 11 vehicle fields keep their own path.
"""
import re

# (target, field, label shown in the reply, spoken names as regex). More specific names first.
FIELDS = (
    ('car', 'price_georgia', 'Цена Грузии', r'(?:цен[аыу]|цін[аиу]|стоимост[ьи]|вартіст[ьі])\s+(?:(?:в|у|для)\s+)?(?:грузи[ия]|грузі[їі])'),
    ('car', 'price_uah', 'Цена Украины', r'(?:цен[аыу]|цін[аиу]|стоимост[ьи]|вартіст[ьі])(?:\s+(?:(?:в|у|для)\s+)?украин[аеыі]|\s+україн[аиі])?'),
    ('car', 'auto_number', 'Номер авто', r'номер\s+(?:авто(?:мобил[яі])?|машины|машини|карточки|картки)'),
    ('car', 'diag_text', 'Описание диагностики', r'(?:описани[ея]|опис)\s+діагностики|описани[ея]\s+диагностики|диагностик[аиу]|діагностик[аиу]'),
    ('car', 'diag_link', 'Ссылка на отчёт', r'(?:ссылк[аиу]|посиланн[яі])\s+на\s+(?:отч[её]т|звіт)'),
    ('car', 'condition_text', 'Описание', r'(?:техническое\s+состояние|технічний\s+стан|тех\s*состояние|описани[ея]|опис)'),
    ('car', 'sea_container', 'Контейнер', r'(?:номер\s+)?контейнер[аы]?'),
    ('car', 'eta_days', 'Срок доставки', r'(?:срок|термін)\s+доставки|(?:дней|днів)\s+до\s+(?:киева|києва)|до\s+(?:киева|києва)\s+(?:осталось|залишилось)'),
    ('client', 'name', 'Покупатель', r'(?:имя|ім.я)\s+(?:клиента|покупателя|клієнта|покупця)|покупател[ья]|покупець'),
    ('client', 'phone', 'Телефон покупателя', r'(?:номер\s+)?телефон[аи]?(?:\s+(?:клиента|покупателя|клієнта|покупця))?'),
    ('client', 'telegram', 'Telegram покупателя', r'телеграм[аи]?(?:\s+(?:клиента|покупателя|клієнта|покупця))?'),
    ('client', 'prepayment', 'Предоплата', r'предоплат[аыу]|передоплат[аиу]|аванс'),
    ('client', 'wishes', 'Заметка', r'заметк[аиу]|примечани[ея]|нотатк[аиу]|побажанн[яі]|пожелани[ея]'),
)
LABELS = {field: label for _, field, label, _ in FIELDS}
# Free text runs to the next field name; other values end at the first clause break.
FREE_TEXT = frozenset(('condition_text', 'diag_text', 'wishes'))
_CLAUSE = re.compile(r'[,;]\s|\.(?:\s|$)')
_EDGE = r'(?<![а-яіїєґa-z0-9])(?:%s)(?![а-яіїєґa-z0-9])'
_PATTERNS = [(target, field, re.compile(_EDGE % pattern, re.I)) for target, field, _, pattern in FIELDS]
# Words that only join a name to its value: «цена Грузии — это 17 500», «телефон: …».
_LEAD = re.compile(r'^(?:[\s:=,.;—–-]|(?:на|это|будет|буде|составляет|становить|равна|равен|дорівнює)(?![а-яіїєґa-z]))+', re.I)
_TAIL = re.compile(r'[\s,.;:—–-]+$')


def parse(text):
    """Return ([(target, field, value)], the text no field took). The first value of a field wins."""
    text = str(text or '')
    found = []
    for order, (target, field, pattern) in enumerate(_PATTERNS):
        for match in pattern.finditer(text):
            found.append((match.start(), -(match.end() - match.start()), order, match.end(), target, field))
    names, end = [], -1
    for start, _, _, stop, target, field in sorted(found):
        if start >= end:  # the longest name at a position; overlapping shorter names are ignored
            names.append((start, stop, target, field))
            end = stop
    commands, seen, taken = [], set(), []
    for number, (start, stop, target, field) in enumerate(names):
        following = names[number + 1][0] if number + 1 < len(names) else len(text)
        if field not in FREE_TEXT:
            clause = _CLAUSE.search(text, stop, following)
            following = clause.start() if clause else following
        value = _TAIL.sub('', _LEAD.sub('', text[stop:following]))
        taken.append((start, following))
        if value and (target, field) not in seen:
            seen.add((target, field))
            commands.append((target, field, value))
    rest, position = [], 0
    for start, stop in taken:
        rest.append(text[position:start])
        position = stop
    rest.append(text[position:])
    return commands, ' '.join(' '.join(rest).split()).strip(' ,.;')
