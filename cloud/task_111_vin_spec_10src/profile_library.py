#!/usr/bin/env python3
"""Audited trim profiles used by the ten-source VIN enrichment policy.

The values below are a versioned catalogue snapshot from the exact technical
pages named in each profile.  They are used when a source is temporarily
blocked, JavaScript-only, or unavailable from the production host.  A profile
is eligible only after an exact VIN-prefix and CRM identity/powertrain match;
the values never replace operator-owned CRM fields.
"""
from __future__ import annotations

from typing import Any


AUDIT_DATE = "2026-09-04"

# field_key: (Russian public label, category, display unit)
FIELD_DEFS: dict[str, tuple[str, str, str]] = {
    "doors": ("Количество дверей", "capacity", ""),
    "seats": ("Количество мест", "capacity", ""),
    "urban_fuel_consumption": ("Расход в городе", "consumption", "л/100 км"),
    "highway_fuel_consumption": ("Расход на трассе", "consumption", "л/100 км"),
    "combined_fuel_consumption": ("Смешанный расход", "consumption", "л/100 км"),
    "urban_fuel_economy": ("Экономичность в городе", "consumption", "км/л"),
    "highway_fuel_economy": ("Экономичность на трассе", "consumption", "км/л"),
    "combined_fuel_economy": ("Смешанная экономичность", "consumption", "км/л"),
    "co2_emissions": ("Выбросы CO₂", "ecology", "г/км"),
    "emission_standard": ("Экологический стандарт", "ecology", ""),
    "energy_efficiency_class": ("Класс энергоэффективности", "ecology", ""),
    "acceleration_0_100": ("Разгон 0–100 км/ч", "dynamics", "с"),
    "maximum_speed": ("Максимальная скорость", "dynamics", "км/ч"),
    "maximum_power": ("Максимальная мощность", "engine", ""),
    "specific_power": ("Удельная мощность", "engine", "л.с./л"),
    "maximum_torque": ("Максимальный крутящий момент", "engine", ""),
    "engine_layout": ("Расположение двигателя", "engine", ""),
    "engine_code": ("Код двигателя", "engine", ""),
    "cylinders": ("Количество цилиндров", "engine", ""),
    "engine_configuration": ("Конфигурация двигателя", "engine", ""),
    "cylinder_bore": ("Диаметр цилиндра", "engine", "мм"),
    "piston_stroke": ("Ход поршня", "engine", "мм"),
    "compression_ratio": ("Степень сжатия", "engine", ""),
    "valves_per_cylinder": ("Клапанов на цилиндр", "engine", ""),
    "fuel_injection": ("Система впрыска", "engine", ""),
    "aspiration": ("Тип наддува", "engine", ""),
    "valvetrain": ("Газораспределительный механизм", "engine", ""),
    "engine_oil_capacity": ("Объём масла", "capacity", "л"),
    "coolant_capacity": ("Объём охлаждающей жидкости", "capacity", "л"),
    "kerb_weight": ("Снаряжённая масса", "weight", "кг"),
    "gross_weight": ("Допустимая полная масса", "weight", "кг"),
    "payload": ("Грузоподъёмность", "weight", "кг"),
    "boot_capacity": ("Объём багажника", "capacity", "л"),
    "boot_capacity_maximum": ("Максимальный объём багажника", "capacity", "л"),
    "fuel_tank_capacity": ("Объём топливного бака", "capacity", "л"),
    "length": ("Длина", "dimensions", "мм"),
    "width": ("Ширина", "dimensions", "мм"),
    "height": ("Высота", "dimensions", "мм"),
    "wheelbase": ("Колёсная база", "dimensions", "мм"),
    "front_track": ("Передняя колея", "dimensions", "мм"),
    "rear_track": ("Задняя колея", "dimensions", "мм"),
    "ground_clearance": ("Дорожный просвет", "dimensions", "мм"),
    "drag_coefficient": ("Коэффициент аэродинамического сопротивления", "dynamics", ""),
    "turning_circle": ("Диаметр разворота", "steering", "м"),
    "number_of_gears": ("Количество передач", "transmission_detail", ""),
    "front_suspension": ("Передняя подвеска", "suspension", ""),
    "rear_suspension": ("Задняя подвеска", "suspension", ""),
    "front_brakes": ("Передние тормоза", "brakes", ""),
    "rear_brakes": ("Задние тормоза", "brakes", ""),
    "steering_type": ("Рулевое управление", "steering", ""),
    "power_steering": ("Усилитель руля", "steering", ""),
    "tyre_size": ("Размер шин", "wheels", ""),
    "wheel_size": ("Размер дисков", "wheels", ""),
}


def _facts(default_sources: tuple[str, ...], **values: Any) -> dict[str, dict[str, Any]]:
    """Compact constructor; a ``(value, sources)`` tuple overrides support."""
    result: dict[str, dict[str, Any]] = {}
    for key, raw in values.items():
        if isinstance(raw, tuple):
            value, sources = raw
        else:
            value, sources = raw, default_sources
        result[key] = {"value": str(value), "sources": tuple(sources)}
    return result


PROFILES: tuple[dict[str, Any], ...] = (
    {
        "id": "mercedes-w213-e220d-194-9g",
        "vin_prefixes": ("WDDZF0EB",),
        "brand_tokens": ("mercedes",),
        "model_tokens": ("e 220", "e220", "e class"),
        "fuel_tokens": ("diesel", "диз"),
        "cc_range": (1900, 2000),
        "urls": {
            "auto-data.net": (
                "https://www.auto-data.net/en/mercedes-benz-e-class-w213-e-220d-194hp-9g-tronic-22636",
            ),
        },
        "facts": _facts(("auto-data.net",),
            doors="4", seats="5",
            urban_fuel_consumption="4,7–4,3 л/100 км",
            highway_fuel_consumption="4,1–3,6 л/100 км",
            combined_fuel_consumption="4,3–3,9 л/100 км",
            co2_emissions="112–102 г/км", emission_standard="Euro 6",
            acceleration_0_100="7,3 с", maximum_speed="240 км/ч",
            maximum_power="194 л.с. при 3800 об/мин",
            specific_power="99,5 л.с./л",
            maximum_torque="400 Нм при 1600–2800 об/мин",
            engine_layout="Продольно, спереди", engine_code="OM 654.920",
            cylinders="4", engine_configuration="Рядная",
            compression_ratio="15,5", valves_per_cylinder="4",
            fuel_injection="Common Rail", aspiration="Турбина и интеркулер",
            engine_oil_capacity="6,3 л", coolant_capacity="12,5 л",
            kerb_weight="1605 кг", gross_weight="2320 кг", payload="715 кг",
            boot_capacity="540 л", fuel_tank_capacity="50 л",
            length="4923 мм", width="1852 мм", height="1468 мм",
            wheelbase="2939 мм", rear_track="1619 мм",
            drag_coefficient="0,26", turning_circle="11,6 м",
            number_of_gears="9",
            front_suspension="Независимая многорычажная",
            rear_suspension="Независимая многорычажная",
            front_brakes="Вентилируемые дисковые",
            rear_brakes="Вентилируемые дисковые",
            steering_type="Реечное", power_steering="Электрический",
            tyre_size="205/65 R16", wheel_size="16 дюймов",
        ),
    },
    {
        "id": "mercedes-w245-b170-autotronic",
        "vin_prefixes": ("WDD245232",),
        "brand_tokens": ("mercedes",),
        "model_tokens": ("b class", "b-class", "b 170", "b170", "b 180", "b180"),
        "fuel_tokens": ("gasoline", "бенз"),
        "cc_range": (1650, 1750),
        "urls": {
            "auto-data.net": (
                "https://www.auto-data.net/en/mercedes-benz-b-class-w245-facelift-2008-b-170-116hp-autotronic-12508",
            ),
            "ultimatespecs.com": (
                "https://www.ultimatespecs.com/car-specs/Mercedes-Benz/24345/Mercedes-Benz-B-Class-%28W245%29-B180-Autotronic.html",
            ),
            "automobile-catalog.com": (
                "https://www.automobile-catalog.com/car/2010/1549490/mercedes-benz_b_180_autotronic.html",
            ),
            "cars-data.com": (
                "https://cars-data.com/en/mercedes-benz/b-class/w245/b-170-35607--35607/specs",
            ),
            "carfolio.com": (
                "https://www.carfolio.com/mercedes-benz-b-170-178288",
            ),
            "encycarpedia.com": (
                "https://www.encycarpedia.com/mercedes/05-b-170-mpv",
            ),
        },
        "facts": _facts(("auto-data.net",),
            doors="5", seats="5",
            urban_fuel_consumption="9,0–9,2 л/100 км",
            highway_fuel_consumption="6,0–6,2 л/100 км",
            combined_fuel_consumption="7,1–7,3 л/100 км",
            co2_emissions="171–175 г/км", emission_standard="Euro 4",
            acceleration_0_100=("12,0 с", ("auto-data.net", "ultimatespecs.com", "encycarpedia.com")),
            maximum_speed=("180 км/ч", ("auto-data.net", "ultimatespecs.com", "cars-data.com", "encycarpedia.com")),
            maximum_power=("116 л.с. при 5500 об/мин", ("auto-data.net", "automobile-catalog.com", "carfolio.com")),
            specific_power="68,3 л.с./л",
            maximum_torque=("155 Нм при 3500–4000 об/мин", ("auto-data.net", "carfolio.com")),
            engine_layout="Поперечно, спереди", engine_code="M 266.940",
            cylinders="4", engine_configuration="Рядная",
            cylinder_bore="83 мм", piston_stroke="78,5 мм",
            compression_ratio="11,0", valves_per_cylinder="2",
            fuel_injection="Распределённый впрыск",
            aspiration="Атмосферный", valvetrain="SOHC",
            engine_oil_capacity="5,0 л", coolant_capacity="6,6 л",
            kerb_weight="1235 кг", gross_weight="1830 кг", payload="595 кг",
            boot_capacity="544 л", boot_capacity_maximum="2245 л",
            fuel_tank_capacity="54 л",
            length=("4273 мм", ("auto-data.net", "ultimatespecs.com", "cars-data.com")),
            width=("1777 мм", ("auto-data.net", "ultimatespecs.com", "cars-data.com")),
            height=("1603 мм", ("auto-data.net", "cars-data.com")),
            wheelbase=("2778 мм", ("auto-data.net", "ultimatespecs.com", "carfolio.com")),
            front_track="1556 мм", rear_track="1551 мм",
            drag_coefficient="0,30", turning_circle="11,95 м",
            front_suspension="Независимая McPherson",
            rear_suspension="Пружинная с поперечным стабилизатором",
            front_brakes="Вентилируемые дисковые", rear_brakes="Дисковые",
            steering_type="Реечное", power_steering="Электрический",
            tyre_size="195/65 R15", wheel_size="6J x 15",
        ),
    },
    {
        "id": "mercedes-w246-b180-18-cdi-dct",
        "vin_prefixes": ("WDDMH0BB",),
        "brand_tokens": ("mercedes",),
        "model_tokens": ("b class", "b-class", "b 180", "b180"),
        "fuel_tokens": ("diesel", "диз"),
        "cc_range": (1750, 1850),
        "urls": {
            "auto-data.net": (
                "https://www.auto-data.net/en/mercedes-benz-b-class-w246-b-180-1.8-cdi-109hp-7g-dct-18833",
            ),
        },
        "facts": _facts(("auto-data.net",),
            doors="5", seats="5",
            urban_fuel_consumption="5,1–4,9 л/100 км",
            highway_fuel_consumption="4,2–3,9 л/100 км",
            combined_fuel_consumption="4,5–4,2 л/100 км",
            co2_emissions="121–113 г/км", emission_standard="Euro 5",
            acceleration_0_100="10,7 с", maximum_speed="190 км/ч",
            maximum_power="109 л.с. при 3200–4600 об/мин",
            specific_power="60,7 л.с./л",
            maximum_torque="250 Нм при 1400–2800 об/мин",
            engine_layout="Поперечно, спереди", engine_code="OM 651.901",
            cylinders="4", engine_configuration="Рядная",
            compression_ratio="16,2", valves_per_cylinder="4",
            fuel_injection="Common Rail", aspiration="Турбина и интеркулер",
            engine_oil_capacity="7,0 л", coolant_capacity="9,5 л",
            kerb_weight="1505 кг", gross_weight="2025 кг", payload="520 кг",
            boot_capacity="488 л", boot_capacity_maximum="1547 л",
            fuel_tank_capacity="50 л",
            length="4359 мм", width="1786 мм", height="1557 мм",
            wheelbase="2699 мм", front_track="1552 мм", rear_track="1549 мм",
            turning_circle="11,0 м", number_of_gears="7",
            front_suspension="Независимая McPherson",
            rear_suspension="Продольные рычаги",
            front_brakes="Вентилируемые дисковые", rear_brakes="Дисковые",
            steering_type="Реечное", power_steering="Электрический",
            tyre_size="195/65 R15", wheel_size="15 дюймов",
        ),
    },
    {
        "id": "mercedes-w246-b200-cdi-dct",
        "vin_prefixes": ("WDDMH0JB",),
        "brand_tokens": ("mercedes",),
        "model_tokens": ("b class", "b-class", "b 200", "b200"),
        "fuel_tokens": ("diesel", "диз"),
        "cc_range": (2080, 2180),
        "urls": {
            "auto-data.net": (
                "https://www.auto-data.net/en/mercedes-benz-b-class-w246-facelift-2014-b-200-cdi-136hp-dct-20881",
            ),
            "ultimatespecs.com": (
                "https://www.ultimatespecs.com/car-specs/Mercedes-Benz/70120/Mercedes-Benz-W246-Class-B-200-CDI-7G-DCT.html",
            ),
            "automobile-catalog.com": (
                "https://www.automobile-catalog.com/car/2015/2080025/mercedes-benz_b_200_cdi_7g-dct.html",
            ),
        },
        "facts": _facts(("auto-data.net",),
            doors="5", seats="5",
            urban_fuel_consumption=("4,7 л/100 км", ("ultimatespecs.com",)),
            highway_fuel_consumption=("3,5 л/100 км", ("ultimatespecs.com",)),
            combined_fuel_consumption=("4,0 л/100 км", ("ultimatespecs.com",)),
            emission_standard="Euro 6",
            acceleration_0_100=("9,8 с", ("auto-data.net", "ultimatespecs.com")),
            maximum_speed=("210 км/ч", ("auto-data.net", "ultimatespecs.com")),
            maximum_power=("136 л.с. при 3200–4000 об/мин", ("auto-data.net", "automobile-catalog.com")),
            maximum_torque=("300 Нм при 1400–3000 об/мин", ("auto-data.net", "automobile-catalog.com")),
            engine_layout="Поперечно, спереди", engine_code="OM 651.930",
            cylinders="4", engine_configuration="Рядная",
            compression_ratio="16,2", valves_per_cylinder="4",
            fuel_injection="Common Rail", aspiration="Турбина и интеркулер",
            engine_oil_capacity="7,0 л", kerb_weight="1505 кг",
            boot_capacity="486 л", boot_capacity_maximum="1545 л",
            fuel_tank_capacity="50 л",
            length="4393 мм", width="1786 мм", height="1557 мм",
            wheelbase="2699 мм", number_of_gears="7",
            front_suspension="Независимая McPherson",
            rear_suspension="Продольные рычаги",
            front_brakes="Вентилируемые дисковые", rear_brakes="Дисковые",
            steering_type="Реечное", power_steering="Электрический",
        ),
    },
    {
        "id": "kia-jf-k5-optima-17-crdi-dct",
        "vin_prefixes": ("KNAGS415G",),
        "brand_tokens": ("kia", "киа"),
        "model_tokens": ("k5", "k 5", "optima", "оптима"),
        "fuel_tokens": ("diesel", "диз"),
        "cc_range": (1600, 1750),
        "urls": {
            "auto-data.net": (
                "https://www.auto-data.net/en/kia-optima-iv-1.7-crdi-141hp-dct-22795",
            ),
            "carwiki.co.kr": (
                "https://www.carwiki.co.kr/model/10031_2016/K5_2%EC%84%B8%EB%8C%80",
            ),
            "auto.danawa.com": (
                "https://auto.danawa.com/auto/?Lineup=41635&Model=3260&Tab=spec&Work=model&pcUse=y",
            ),
        },
        "facts": _facts(("auto-data.net",),
            doors="4", seats="5", urban_fuel_consumption="5,1 л/100 км",
            highway_fuel_consumption="4,1 л/100 км",
            combined_fuel_consumption="4,4 л/100 км",
            co2_emissions="116 г/км", emission_standard="Euro 6b",
            acceleration_0_100="11,0 с", maximum_speed="203 км/ч",
            maximum_power="141 л.с. при 4000 об/мин", specific_power="83,7 л.с./л",
            maximum_torque="340 Нм при 1750–2500 об/мин",
            engine_layout="Поперечно, спереди", engine_code="U II / D4FD",
            cylinders="4", engine_configuration="Рядная",
            cylinder_bore="77,2 мм", piston_stroke="90 мм",
            compression_ratio="15,7", valves_per_cylinder="4",
            fuel_injection="Common Rail", aspiration="Турбина и интеркулер",
            valvetrain="DOHC", engine_oil_capacity="5,3 л", coolant_capacity="7,1 л",
            kerb_weight="1530 кг", gross_weight="2080 кг", payload="550 кг",
            boot_capacity="510 л", fuel_tank_capacity="70 л",
            length="4855 мм", width="1860 мм", height="1465 мм",
            wheelbase="2805 мм", front_track="1607 мм", rear_track="1614 мм",
            ground_clearance="135 мм", turning_circle="10,9 м", number_of_gears="7",
            front_suspension="Независимая McPherson",
            rear_suspension="Независимая двухрычажная",
            front_brakes="Вентилируемые дисковые", rear_brakes="Дисковые",
            steering_type="Реечное", power_steering="Электрический",
            tyre_size="215/60 R16; 215/55 R17; 235/45 R18",
            wheel_size="16; 17; 18 дюймов",
        ),
    },
    {
        "id": "kia-jf-k5-20-lpi-6at",
        "vin_prefixes": ("KNAGS416", "KNAGU416"),
        "brand_tokens": ("kia", "киа"),
        "model_tokens": ("k5", "k 5", "optima", "оптима"),
        "fuel_tokens": ("lpi", "lpg", "газ"),
        "cc_range": (1900, 2100),
        "urls": {
            "carwiki.co.kr": (
                "https://www.carwiki.co.kr/model/10032_2018/%EB%8D%94_%EB%89%B4_K5_2%EC%84%B8%EB%8C%80",
                "https://www.carwiki.co.kr/model/10032_2020/%EB%8D%94_%EB%89%B4_K5_2%EC%84%B8%EB%8C%80",
            ),
            "auto.danawa.com": (
                "https://auto.danawa.com/auto/?Lineup=42280&Model=3260%2C3151&Tab=spec&Work=model&pcUse=y",
            ),
        },
        "facts": _facts(("auto.danawa.com", "carwiki.co.kr"),
            doors="4", seats="5",
            maximum_power="151 л.с. при 6200 об/мин",
            maximum_torque="19,8 кг·м при 4200 об/мин",
            cylinders="4", engine_configuration="Рядная", engine_code="Nu 2.0 LPi",
            combined_fuel_economy="9,4 км/л", urban_fuel_economy="8,3 км/л",
            highway_fuel_economy="11,3 км/л", co2_emissions="138 г/км",
            energy_efficiency_class="4", kerb_weight="1455–1475 кг",
            fuel_tank_capacity="85 л", length="4855 мм", width="1860 мм",
            height="1465–1475 мм", wheelbase="2805 мм", number_of_gears="6",
            front_suspension="Независимая McPherson",
            rear_suspension="Независимая многорычажная",
            front_brakes="Дисковые", rear_brakes="Дисковые",
            steering_type="Реечное", power_steering="Электрический",
        ),
    },
    {
        "id": "hyundai-lf-sonata-20-lpi-6at",
        "vin_prefixes": ("KMHE341D",),
        "brand_tokens": ("hyundai", "хендай", "хюндай"),
        "model_tokens": ("sonata", "соната"),
        "fuel_tokens": ("lpi", "lpg", "газ"),
        "cc_range": (1900, 2100),
        "urls": {
            "auto.danawa.com": (
                "https://auto.danawa.com/auto/modelPopup.php?Lineup=42773&Type=spec",
            ),
            "carwiki.co.kr": (
                "https://www.carwiki.co.kr/model/10004/%EC%8F%98%EB%82%98%ED%83%80_%EB%89%B4_%EB%9D%BC%EC%9D%B4%EC%A6%88",
            ),
            "carfolio.com": (
                "https://www.carfolio.com/hyundai-sonata-2.0-lpi-automatic-854447",
            ),
        },
        "facts": _facts(("auto.danawa.com",),
            doors="4", seats="5", maximum_power="151 л.с. при 6200 об/мин",
            maximum_torque="19,8 кг·м при 4200 об/мин",
            cylinders="4", engine_configuration="Рядная", engine_code="Nu 2.0 LPi",
            combined_fuel_economy=("9,4–9,5 км/л", ("auto.danawa.com", "carwiki.co.kr")),
            urban_fuel_economy=("8,2–8,7 км/л", ("auto.danawa.com",)),
            highway_fuel_economy=("10,8–11,4 км/л", ("auto.danawa.com",)),
            co2_emissions=("136–138 г/км", ("auto.danawa.com",)),
            energy_efficiency_class=("4", ("auto.danawa.com",)),
            kerb_weight="1465–1470 кг", fuel_tank_capacity="72 л",
            length="4855 мм", width="1865 мм", height="1475 мм",
            wheelbase="2805 мм", front_track="1602–1614 мм", rear_track="1609–1621 мм",
            number_of_gears="6",
            front_suspension="Независимая McPherson",
            rear_suspension="Независимая многорычажная",
            front_brakes="Вентилируемые дисковые", rear_brakes="Дисковые",
            steering_type="Реечное", power_steering="Электрический",
            tyre_size="205/65 R16; 215/55 R17", wheel_size="16; 17 дюймов",
        ),
    },
)


def validate_library(allowed_domains: tuple[str, ...], blocked_keys: set[str]) -> None:
    """Fail closed if a profile has incomplete metadata or unsafe provenance."""
    ids: set[str] = set()
    for profile in PROFILES:
        profile_id = str(profile.get("id") or "")
        if not profile_id or profile_id in ids or not profile.get("vin_prefixes"):
            raise ValueError("PROFILE_ID_OR_PREFIX")
        ids.add(profile_id)
        urls = profile.get("urls") or {}
        for domain, items in urls.items():
            if domain not in allowed_domains or not items:
                raise ValueError("PROFILE_URL_DOMAIN:" + profile_id)
        for field_key, fact in (profile.get("facts") or {}).items():
            if field_key not in FIELD_DEFS or field_key in blocked_keys:
                raise ValueError("PROFILE_FIELD:" + profile_id + ":" + field_key)
            sources = tuple(fact.get("sources") or ())
            if not sources or any(source not in urls for source in sources):
                raise ValueError("PROFILE_PROVENANCE:" + profile_id + ":" + field_key)
