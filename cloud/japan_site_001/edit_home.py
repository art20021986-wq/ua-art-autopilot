"""video/index.html: two stage tile titles with Japan (JAPAN-STOCK-001 step 2, owner «Да» 2026-11-26).

The page is a static file; the counters (ua_site_counters.patch_home) change only each tile's <em> count and the
stage photo only its <img>, so the new titles stay. Russian, Ukrainian and Georgian texts change together.
"""
from edits import replace_once

NAME = 'video/index.html'
PAIRS = (
    ('<b data-ru="Выкуплены и проверены в Корее" data-uk="Викуплені та перевірені в Кореї" '
     'data-ka="კორეაში შეძენილი და შემოწმებული">Викуплені та перевірені в Кореї</b>',
     '<b data-ru="Выкуплены и проверены в Корее и Японии" data-uk="Викуплені та перевірені в Кореї та Японії" '
     'data-ka="კორეასა და იაპონიაში შეძენილი და შემოწმებული">Викуплені та перевірені в Кореї та Японії</b>'),
    ('<b data-ru="На пароме: Корея → Грузия" data-uk="На поромі: Корея → Грузія" '
     'data-ka="ბორანზე: კორეა → საქართველო">На поромі: Корея → Грузія</b>',
     '<b data-ru="На пароме из Кореи и Японии в Грузию" data-uk="На поромі з Кореї та Японії до Грузії" '
     'data-ka="ბორანით კორეიდან და იაპონიიდან საქართველოში">На поромі з Кореї та Японії до Грузії</b>'),
)


def build(source):
    return replace_once(source.decode('utf-8'), PAIRS, NAME).encode('utf-8')
