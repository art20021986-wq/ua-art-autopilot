"""ua_delivery_status.py: Japan stage-1 and ferry choices for the CRM menu (JAPAN-STOCK-001).

The stored stage codes stay the same (a Japanese car is kr_bought / sea_loaded like a Korean one); the country is
kept by ua_car_country. The public labels, statuses, stage numbers and counts do not change.
"""
from edits import replace_once

NAME = 'ua_delivery_status.py'
PAIRS = (
    ('''    ("korea", "kr_bought", 1, "В Корее"),
    ("ferry", "sea_loaded", 2, "На пароме"),
''', '''    ("korea", "kr_bought", 1, "В Корее"),
    ("japan", "kr_bought", 1, "В Японии"),
    ("ferry", "sea_loaded", 2, "Паром Корея"),
    ("ferry_jp", "sea_loaded", 2, "Паром Япония"),
'''),
    ('''def crm_status_from_input(value: object) -> str:
    """Translate a new canonical CRM callback to its existing storage code."""
    return _CRM_CODES.get(normalize_status(value), HIDDEN)
''', '''def crm_status_from_input(value: object) -> str:
    """Translate a CRM menu choice (CHOICES code) to its existing storage code."""
    return _CRM_CODES.get(value, HIDDEN) if isinstance(value, str) else HIDDEN


# JAPAN-STOCK-001: menu choice <-> (stored status, country).
CHOICE_COUNTRY = {"korea": "korea", "japan": "japan", "ferry": "korea", "ferry_jp": "japan"}
_JAPAN_CHOICE = {"korea": "japan", "ferry": "ferry_jp"}
_CHOICE_LABELS = {code: label for code, _, _, label in CHOICES}


def choice_code(status: object, country: object) -> str:
    """The menu choice of a car: its public status, the Japan variant for a Japanese car."""
    public = public_status(status)
    return _JAPAN_CHOICE.get(public, public) if country == "japan" else public


def choice_label(status: object, country: object) -> str | None:
    """The CRM label of a car's stage («В Японии», «Паром Корея», ...); None for a hidden card."""
    return _CHOICE_LABELS.get(choice_code(status, country))
'''),
)


def build(source):
    text = replace_once(source.decode('utf-8'), PAIRS, NAME)
    compile(text, NAME, 'exec')
    return text.encode('utf-8')
