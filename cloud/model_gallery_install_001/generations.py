"""Generation line of each model card (MODEL-GALLERY-001), read from the current main photo of the model.

key -> (generation number, model code or None, first year). A card that is a category, not a model,
names the car on its photo instead.
"""
GENERATIONS = {
    'audi-q5': (1, '8R', 2008),
    'bmw-x3': (4, 'G45', 2024),
    'byd-seal': (1, None, 2022),
    'byd-song-plus': (1, None, 2020),
    'byd-yuan-plus-atto-3': (1, None, 2022),
    'ford-escape': (4, None, 2019),
    'ford-fusion-fusion-hybrid': (2, None, 2012),
    'hyundai-santa-fe': (5, 'MX5', 2023),
    'hyundai-sonata': (8, 'DN8', 2019),
    'hyundai-tucson': (4, 'NX4', 2020),
    'kia-k5': (3, 'DL3', 2019),
    'kia-sportage': (5, 'NQ5', 2021),
    'lexus-rx-350': (3, 'AL10', 2008),
    'lexus-rx-500': (5, None, 2022),
    'lexus-tx': (1, None, 2023),
    'mercedes-benz-b-class': (2, 'W246', 2011),
    'nissan-note': (2, 'E12', 2012),
    'nissan-rogue': (3, 'T33', 2020),
    'renault-megane': (4, None, 2016),
    'skoda-octavia': (4, None, 2019),
    'subaru-forester': (6, 'SL', 2023),
    'tesla-model-3': (1, None, 2017),
    'tesla-model-y': (1, None, 2020),
    'toyota-aqua': (2, None, 2021),
    'toyota-camry': (8, 'XV70', 2017),
    'toyota-prius': (5, 'XW60', 2022),
    'toyota-rav4-rav4-hybrid': (5, 'XA50', 2018),
    'toyota-tacoma-trailhunter': (4, None, 2023),
    'toyota-tacoma-trd-pro': (4, None, 2023),
    'volkswagen-golf': (8, None, 2019),
    'volkswagen-id-4': (1, None, 2020),
    'volkswagen-jetta': (7, None, 2018),
    'volkswagen-tiguan': (3, None, 2023),
    'zeekr-001': (1, None, 2021),
}
PHOTO_OF = {'classics-1980-1990': ('Mercedes-Benz W124', '1984–1997')}
UK_ORDINAL = {1: '1-ше', 2: '2-ге', 3: '3-тє', 4: '4-те', 5: '5-те', 6: '6-те', 7: '7-ме', 8: '8-ме'}


def line(key):
    """The generation line in uk, ru and ka."""
    if key in PHOTO_OF:
        car, years = PHOTO_OF[key]
        return {'uk': 'на фото — %s, %s' % (car, years), 'ru': 'на фото — %s, %s' % (car, years),
                'ka': 'ფოტოზე — %s, %s' % (car, years)}
    number, code, year = GENERATIONS[key]
    code = ' (%s)' % code if code else ''
    return {'uk': '%s покоління%s, з %d р.' % (UK_ORDINAL[number], code, year),
            'ru': '%d-е поколение%s, с %d г.' % (number, code, year),
            'ka': '%s თაობა%s, %d წლიდან' % ('პირველი' if number == 1 else 'მე-%d' % number, code, year)}
