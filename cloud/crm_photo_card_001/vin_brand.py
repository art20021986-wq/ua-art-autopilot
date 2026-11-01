"""Manufacturer from a VIN's World Manufacturer Identifier (ISO 3780: the first three characters).

Only exact, unambiguous WMIs of brands the CRM already knows. An unknown WMI gives None:
no guessing from partial codes.
"""
WMI = {
    'Mercedes-Benz': ('WDB', 'WDC', 'WDD', 'WDF', 'W1K', 'W1N', 'W1V'),
    'BMW': ('WBA', 'WBS', 'WBX', 'WBY', '5UX'),
    'Audi': ('WAU', 'WA1', 'TRU'),
    'Volkswagen': ('WVW', 'WVG', 'WV1', 'WV2'),
    'Skoda': ('TMB',),
    'Kia': ('KNA', 'KNC', 'KND', 'KNE', 'KNM'),
    'Hyundai': ('KMH', 'KMF', 'KM8'),
    'Genesis': ('KMT',),
    'Toyota': ('JTD', 'JTE', 'JTM', 'JTN', '4T1'),
    'Lexus': ('JTH', 'JTJ'),
    'Nissan': ('JN1', 'JN8'),
    'Honda': ('JHM', 'JHL'),
    'Mazda': ('JM1', 'JM3'),
    'Subaru': ('JF1', 'JF2'),
    'Mitsubishi': ('JA3', 'JA4', 'JMB'),
    'Ford': ('WF0', '1FA', '1FM'),
    'Renault': ('VF1',),
    'Peugeot': ('VF3',),
    'Citroen': ('VF7',),
    'Volvo': ('YV1',),
}
_BY_WMI = {code: brand for brand, codes in WMI.items() for code in codes}


def brand(vin):
    return _BY_WMI.get(str(vin or '').strip().upper()[:3])
