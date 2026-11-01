"""Marketplace screenshots put a field's value on the line under its label (AUTO.RIA layout).

``join_labels`` rewrites such pairs as ``label: value`` lines, the form the existing CRM
parsers already read. Labels are mapped to the Russian names those parsers know. Pure text
in, text out: no OCR, database or Telegram.
"""
import re

# Screen label (UK/RU, lower case) -> label understood by the existing parsers.
LABELS = {
    'двигун': 'двигатель', 'двигатель': 'двигатель',
    'коробка передач': 'коробка передач',
    'привід': 'привод', 'привод': 'привод',
    'колір': 'цвет', 'цвет': 'цвет',
    'пробіг': 'пробег', 'пробег': 'пробег',
    'рік випуску': 'год', 'год выпуска': 'год',
    'технічний стан': 'состояние', 'техническое состояние': 'состояние', 'техстан': 'состояние',
}
_SPACES = re.compile(r'\s+')
_WORD = re.compile(r'\w\w')  # an OCR fragment shorter than two letters/digits is not a value


def _label(line):
    return LABELS.get(_SPACES.sub(' ', line).strip(' :').casefold())


def join_labels(text):
    """Return ``label: value`` lines for known labels followed by a value line.

    The first value of a label wins: OCR passes are ordered from the whole page to its parts,
    so later occurrences are partial re-reads.
    """
    lines = [line.strip() for line in str(text or '').splitlines() if line.strip()]
    pairs = {}
    for label_line, value in zip(lines, lines[1:]):
        label = _label(label_line)
        if label and label not in pairs and not _label(value) and _WORD.search(value):
            pairs[label] = value
    return '\n'.join('%s: %s' % pair for pair in pairs.items())
