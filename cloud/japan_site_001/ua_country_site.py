"""Country texts of the public pages (JAPAN-STOCK-001 step 2, owner «Да» 2026-11-26).

One place for what the site says about a car's country: the card chip «Автомобиль из Кореи/Японии», the Japan
versions of the stage-1 and ferry texts, and the catalog status of a car bought in Japan. Korean texts stay the
exact texts the pages have now; the country itself comes from ua_car_country (no record = Korea).
Every visible Japan text carries data-ru/data-uk, so the language switch and the ua/ru page copies translate it.
"""
import html

KOREA = 'korea'
JAPAN = 'japan'
COUNTRY_CHIP = {KOREA: ('🇰🇷 Автомобиль из Кореи', '🇰🇷 Автомобіль з Кореї'),
                JAPAN: ('🇯🇵 Автомобиль из Японии', '🇯🇵 Автомобіль з Японії')}
# Existing Korean text -> its Japan version (ru, uk).
_JAPAN_TEXT = {
    'Выкуплена · стоянка в Корее': ('Выкуплена · стоянка в Японии', 'Викуплена · стоянка в Японії'),
    'На пароме · Корея → Грузия': ('На пароме · Япония → Грузия', 'На поромі · Японія → Грузія'),
    'Выкуплен · стоянка в Корее': ('Выкуплен · стоянка в Японии', 'Викуплений · стоянка в Японії'),
    'Паром · Корея → Грузия': ('Паром · Япония → Грузия', 'Пором · Японія → Грузія'),
    'Корея': ('Япония', 'Японія'),
}
_ICONS = ('🇰🇷', '🚢', '📋', '📍')
CATALOG_JAPAN_LABEL = ('В Японии · выкуплен и проверен', 'У Японії · викуплений і перевірений')


def _e(value):
    return html.escape(str(value), quote=True)


def country(car):
    """The car's country by its CRM id (rows of the cars table)."""
    import ua_car_country
    return ua_car_country.country_of(car['id']) if car.get('id') is not None else KOREA


def japan_ids():
    import ua_car_country
    return ua_car_country.japan_ids()


def _japan(text, country_code):
    """The Japan version (ru, uk) of a Korean text; None for a Korean car or another text."""
    return _JAPAN_TEXT.get(text) if country_code == JAPAN else None


def country_chip(car):
    ru, uk = COUNTRY_CHIP[country(car)]
    return "<div class='chip' data-ru='%s' data-uk='%s'>%s</div>" % (_e(ru), _e(uk), _e(ru))


def stage_chip(car, text):
    pair = _japan(text, country(car))
    if not pair:
        return "<div class='chip'>%s</div>" % _e(text)
    return "<div class='chip' data-ru='%s' data-uk='%s'>%s</div>" % (_e(pair[0]), _e(pair[1]), _e(pair[0]))


def _span(text, country_code):
    pair = _japan(text, country_code)
    if not pair:
        return text
    return '<span data-ru="%s" data-uk="%s">%s</span>' % (_e(pair[0]), _e(pair[1]), _e(pair[0]))


def stage_name(label, country_code):
    """Visible name of a step of «Путь автомобиля» (its data-ua-stage-label stays «Корея»)."""
    return _span(label, country_code)


def current_stage(stage, detail, country_code):
    """(icon, text) of the «ТЕКУЩИЙ ЭТАП» line."""
    icon = '🇯🇵' if country_code == JAPAN and stage == 1 else _ICONS[stage - 1]
    return icon, _span(detail, country_code)
