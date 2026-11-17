"""Korea page lot window: «Привід» and «Колір» right after «КПП» (KOREA-DRIVE-001, owner 2026-11-17).

The values are the lot list's `drive` key (korea_auction/drive.py: повний / передній / задній, or «одна вісь (2WD)»
when the auction writes only 2WD) and `color` key (korea_auction/color.py). No key — no row. Every other byte of
video/korea.html stays; each edit must match exactly once.
"""
DRIVE_WORDS = (('drive', 'Привід', 'Привод', 'ამძრავი'),
         ('drive_full', 'повний', 'полный', 'სრული'),
         ('drive_front', 'передній', 'передний', 'წინა'),
         ('drive_rear', 'задній', 'задний', 'უკანა'),
         ('drive_two', 'одна вісь (2WD)', 'одна ось (2WD)', 'ერთი ღერძი (2WD)'))
COLOR_WORDS = (('color', 'Колір', 'Цвет', 'ფერი'),
               ('color_white', 'білий', 'белый', 'თეთრი'), ('color_black', 'чорний', 'черный', 'შავი'),
               ('color_gray', 'сірий', 'серый', 'ნაცრისფერი'), ('color_silver', 'сріблястий', 'серебристый', 'ვერცხლისფერი'),
               ('color_blue', 'синій', 'синий', 'ლურჯი'), ('color_red', 'червоний', 'красный', 'წითელი'),
               ('color_brown', 'коричневий', 'коричневый', 'ყავისფერი'), ('color_beige', 'бежевий', 'бежевый', 'კრემისფერი'),
               ('color_green', 'зелений', 'зеленый', 'მწვანე'), ('color_yellow', 'жовтий', 'желтый', 'ყვითელი'),
               ('color_orange', 'помаранчевий', 'оранжевый', 'ნარინჯისფერი'), ('color_other', 'інший', 'другой', 'სხვა'))
WORDS = DRIVE_WORDS + COLOR_WORDS
LABEL = '"gear": ["КПП", "КПП", "გადაცემათა კოლოფი"],'
ROW = 'row("gear",l.transmission)'
EDITS = (
    (LABEL, LABEL + ''.join(' "%s": ["%s", "%s", "%s"],' % item for item in WORDS)),
    (ROW, ROW + '+drive(l)+color(l)'),
    ('function row(k,v){',
     'function drive(l){return l.drive&&L["drive_"+l.drive]?rowh("drive",t("drive_"+l.drive)):"";}'
     'function color(l){return l.color&&L["color_"+l.color]?rowh("color",t("color_"+l.color)):"";}function row(k,v){'),
)
# Public proof that this release is live.
CHECK = 'function drive(l){'


def build(source):
    text = source.decode('utf-8')
    if CHECK in text or any(text.count(old) != 1 for old, _ in EDITS):
        raise ValueError('DRIVE_ANCHOR')
    for old, new in EDITS:
        text = text.replace(old, new)
    return text.encode('utf-8')
