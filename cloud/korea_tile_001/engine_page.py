"""Korea page lot card: the engine row shows the engine type next to the volume (KOREA-ENGINE-001, owner 2026-11-13).

«Двигун: 2 996 см³ · бензин» (uk/ru/ka). The type is the lot list's `fuel` key (korea_auction/fuel.py); a lot without
it keeps the volume alone. Every other byte of video/korea.html stays; each edit must match exactly once.
"""
FUEL = (('gasoline', 'бензин', 'бензин', 'ბენზინი'), ('diesel', 'дизель', 'дизель', 'დიზელი'),
        ('hybrid', 'гібрид', 'гибрид', 'ჰიბრიდი'), ('electric', 'електро', 'электро', 'ელექტრო'),
        ('lpg', 'газ (LPG)', 'газ (LPG)', 'გაზი (LPG)'), ('hydrogen', 'водень', 'водород', 'წყალბადი'))
LABEL = '"engine": ["Двигун", "Двигатель", "ძრავი"],'
ROW = 'row("engine",l.engine_cc?n(l.engine_cc)+" см³":"")'
EDITS = (
    (LABEL, LABEL + ''.join(' "fuel_%s": ["%s", "%s", "%s"],' % item for item in FUEL)),
    (ROW, 'engine(l)'),
    ('function row(k,v){',
     'function engine(l){var p=[];if(l.engine_cc)p.push(esc(n(l.engine_cc)+" см³"));'
     'if(l.fuel&&L["fuel_"+l.fuel])p.push(t("fuel_"+l.fuel));return p.length?rowh("engine",p.join(" · ")):"";}'
     'function row(k,v){'),
)
# Public proof that this release is live.
CHECK = 'function engine(l){'


def build(source):
    text = source.decode('utf-8')
    if CHECK in text or any(text.count(old) != 1 for old, _ in EDITS):
        raise ValueError('ENGINE_ANCHOR')
    for old, new in EDITS:
        text = text.replace(old, new)
    return text.encode('utf-8')
