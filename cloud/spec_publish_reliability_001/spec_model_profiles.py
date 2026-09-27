"""Audited model facts and identity matching, independent of IO and CRM writes.

The registry is by model family/powertrain, never by a newly added full VIN.
Snapshots carry their original URLs/date. Equipment, wheel-dependent economy,
and ambiguous power/gearbox variants are deliberately absent from model facts.
"""
from __future__ import annotations

import re
import profile_library as legacy

VERSION = "model-spec-2026-09-28-v1"
AUDIT_DATE = "2026-09-27"


def normalize(value):
    text = str(value or "").casefold().replace("ё", "е")
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    # Cyrillic letters in model codes are common operator input.
    text = re.sub(r"(?<!\w)[ак](?=\s*\d)", lambda m: {"а": "a", "к": "k"}[m[0]], text)
    return re.sub(r"[^\w.]+", " ", text).strip()


def fuel_type(value):
    text = normalize(value)
    if any(x in text for x in ("hybrid", "гибрид", "гібрид", "하이브리드")):
        return "hybrid"
    if any(x in text for x in ("lpg", "lpi", "газ", "엘피지")):
        return "lpg"
    if any(x in text for x in ("diesel", "диз", "cdi", "tdi", "디젤")):
        return "diesel"
    if any(x in text for x in ("petrol", "gasoline", "бенз", "가솔린")):
        return "petrol"
    return ""


KIA = "https://www.kia.com/kr/vehicles/k5_bak_20231031/specification"
HYUNDAI = "https://www.hyundai.com/content/dam/hyundai/kr/ko/html/pdf/en-cn-catalog/en-catalog/sonata-catalog-eng.pdf"
AUDI = "https://www.auto-data.net/en/audi-a6-limousine-4g-c7-facelift-2014-3.0-tdi-v6-clean-diesel-218hp-s-tronic-20590"


def _profile(id, brand, models, prefixes, years, fuel, cc, urls, values):
    return dict(id=id, brand_tokens=brand, model_tokens=models, vin_prefixes=prefixes,
                years=years, fuel=fuel, cc_range=cc, urls=urls, audited_at=AUDIT_DATE,
                facts=legacy._facts(tuple(urls)[:1], **values))


MODELS = (
    _profile("kia-dl3-k5-20-lpi", ("kia", "киа", "기아"), ("k5", "k 5"),
             ("KNAG541BB", "KNAG741BB"), (2020, 2023), "lpg", (1990, 2010),
             {"kia.com": (KIA,),
              "carisyou.com": ("https://www.carisyou.com/car/6551/Spec",),
              "auto.danawa.com": ("https://auto.danawa.com/auto/?Lineup=45032&Model=3742&Tab=spec&Work=model",)},
             dict(length="4905 мм", width="1860 мм", height="1445 мм", wheelbase="2850 мм",
                  maximum_power="146 л.с. при 6000 об/мин", maximum_torque="19,5 кгс·м",
                  number_of_gears="6", front_brakes="Вентилируемые дисковые", rear_brakes="Дисковые",
                  front_suspension="МакФерсон", rear_suspension="Многорычажная")),
    _profile("hyundai-dn8-sonata-20-lpi", ("hyundai", "хендай", "хюндай", "현대"),
             ("sonata", "соната", "쏘나타"), ("KMHL341DB",), (2019, 2022), "lpg", (1990, 2010),
             {"hyundai.com": (HYUNDAI,)},
             dict(length="4900 мм", width="1860 мм", height="1445 мм", wheelbase="2840 мм",
                  maximum_power="146 л.с. при 6000 об/мин", maximum_torque="19,5 кгс·м при 4200 об/мин",
                  fuel_tank_capacity="64 л", number_of_gears="6")),
    # WAUZZZ4G is not an engine, body style, power or transmission decoder.
    # These engine fundamentals agree across the 218/272/320 PS 3.0 TDI variants.
    _profile("audi-c7-30-tdi-common", ("audi", "ауди"), ("a6", "a 6"),
             ("WAUZZZ4G",), (2014, 2018), "diesel", (2960, 2975),
             {"auto-data.net": (AUDI,
              "https://www.auto-data.net/en/audi-a6-limousine-4g-c7-facelift-2014-3.0-tdi-v6-clean-diesel-272hp-quattro-s-tronic-20591",
              "https://www.auto-data.net/en/audi-a6-limousine-4g-c7-facelift-2014-3.0-tdi-v6-clean-diesel-320hp-quattro-tiptronic-20592")},
             dict(cylinders="6", engine_configuration="V-образная", engine_layout="Продольно, спереди",
                  cylinder_bore="83 мм", piston_stroke="91,4 мм", valves_per_cylinder="4",
                  fuel_injection="Common Rail", valvetrain="DOHC")),
)

LEGACY_YEARS = {
    "mercedes-w213-e220d-194-9g": (2016, 2020),
    "mercedes-w245-b170-autotronic": (2005, 2011),
    "mercedes-w246-b180-18-cdi-dct": (2011, 2014),
    "mercedes-w246-b200-cdi-dct": (2014, 2018),
    "kia-jf-k5-optima-17-crdi-dct": (2015, 2018),
    "kia-jf-k5-20-lpi-6at": (2015, 2020),
    "hyundai-lf-sonata-20-lpi-6at": (2014, 2020),
}
# These omit trim, transmission, calibration, tyres, economy and equipment.
COMMON_FIELDS = frozenset(("length", "width", "wheelbase", "doors", "seats", "cylinders",
    "engine_configuration", "engine_layout", "cylinder_bore", "piston_stroke",
    "valves_per_cylinder", "fuel_injection", "valvetrain", "front_suspension",
    "rear_suspension", "front_brakes", "rear_brakes", "steering_type"))


def _matches(card, profile):
    vin = str(card.get("vin") or "").strip().upper()
    brand, model = normalize(card.get("brand")), normalize(card.get("model"))
    if model in ("б класса", "б класс", "b класса", "b класс"):
        model = "b class"
    try:
        cc, year = float(card.get("engine_cc") or 0), int(card.get("year") or 0)
    except (ValueError, TypeError):
        return False
    lower, upper = profile["cc_range"]
    first, last = profile.get("years") or LEGACY_YEARS[profile["id"]]
    wanted_fuel = profile.get("fuel") or ("lpg" if "lpi" in profile["id"] else
                    "diesel" if any(x in profile["id"] for x in ("cdi", "crdi", "e220d")) else "petrol")
    return (bool(brand and model) and any(vin.startswith(p) for p in profile["vin_prefixes"])
            and any(normalize(t) in brand for t in profile["brand_tokens"])
            and any(normalize(t) == model for t in profile["model_tokens"])
            and first <= year <= last and lower <= cc <= upper
            and fuel_type(card.get("fuel")) == wanted_fuel)


def resolve(card):
    """Require every matching input; fail closed on ambiguous model families."""
    matches = [p for p in (*MODELS, *legacy.PROFILES) if _matches(card, p)]
    if len(matches) != 1:
        return None
    profile = dict(matches[0])
    if profile in MODELS:
        return profile
    profile["audited_at"] = legacy.AUDIT_DATE
    if str(card.get("vin") or "").upper() not in profile.get("exact_vins", ()):
        profile["id"] += "-common"
        profile["facts"] = {k: v for k, v in profile["facts"].items() if k in COMMON_FIELDS}
    return profile
