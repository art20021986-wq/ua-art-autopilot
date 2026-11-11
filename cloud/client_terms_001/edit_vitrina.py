"""vitrina.py (the client bot's screens, CLIENT-TERMS-001): the client start screen drops its only button
«Условия и гарантии» (a link to info.html; the owner, 2026-11-11: not needed, detailed terms and a contract replace it).
Nothing else changes. The original fragment must occur exactly once and an applied fragment is refused.
"""
NAME = 'vitrina.py'
EDITS = (
    ("        knopki = [\n"
     "            [(\"Условия и гарантии\", \"%s/info.html?v=%d\" % (sajt(), int(time.time())))],\n"
     "        ]\n",
     "        knopki = []  # CLIENT-TERMS-001: «Условия и гарантии» removed (owner 2026-11-11)\n"),
)


def build(source):
    text = source.decode('utf-8')
    for old, new in EDITS:
        if text.count(old) != 1 or new in text:
            raise ValueError('VITRINA_FRAGMENT_NOT_UNIQUE')
        text = text.replace(old, new)
    return text.encode('utf-8')
