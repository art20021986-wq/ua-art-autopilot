"""Buyer searches for the USA and Japan campaigns (owner 2026-11-28: «почему США и Япония ещё не составлен план, и
десятки тысяч»). Pure: no network. Same shape as the Korea plan (cloud/ads_bulk_001/keywords.py): brand × model in every
spelling × buyer phrasings, then «model + year» narrow searches, Ukrainian and Russian. One group per brand and language.
"""
USA = {
    'Ford': (['ford', 'форд'], ['fusion', 'escape', 'explorer', 'edge', 'mustang', 'mustang mach-e', 'f-150', 'focus',
                                'expedition', 'bronco', 'ranger', 'фьюжн', 'фюжн', 'ескейп', 'эскейп', 'експлорер',
                                'эксплорер', 'мустанг', 'фокус']),
    'Chevrolet': (['chevrolet', 'chevy', 'шевроле'], ['malibu', 'equinox', 'bolt', 'volt', 'camaro', 'tahoe', 'traverse',
                                                       'trax', 'blazer', 'silverado', 'cruze', 'малибу', 'вольт', 'болт',
                                                       'камаро', 'тахо', 'еквинокс', 'эквинокс']),
    'Dodge': (['dodge', 'додж'], ['charger', 'challenger', 'durango', 'journey', 'чарджер', 'челленджер', 'дуранго',
                                  'джорни']),
    'Jeep': (['jeep', 'джип'], ['cherokee', 'grand cherokee', 'compass', 'renegade', 'wrangler', 'gladiator', 'чероки',
                                'гранд чероки', 'компас', 'ренегат', 'вранглер', 'рэнглер']),
    'Tesla': (['tesla', 'тесла'], ['model 3', 'model y', 'model s', 'model x', 'cybertruck', 'модель 3', 'модель y']),
    'Toyota': (['toyota', 'тойота'], ['camry', 'rav4', 'highlander', 'corolla', 'prius', 'tacoma', 'sienna', 'tundra',
                                      'venza', 'sequoia', 'камри', 'рав4', 'хайлендер', 'королла', 'приус']),
    'Honda': (['honda', 'хонда'], ['accord', 'civic', 'cr-v', 'pilot', 'hr-v', 'odyssey', 'passport', 'аккорд', 'цивик',
                                   'срв', 'пайлот']),
    'Nissan': (['nissan', 'ниссан', 'нісан'], ['rogue', 'altima', 'sentra', 'leaf', 'murano', 'pathfinder', 'kicks',
                                               'armada', 'frontier', 'роуг', 'альтима', 'сентра', 'лиф', 'мурано',
                                               'патфайндер']),
    'Hyundai': (['hyundai', 'хюндай', 'хендай'], ['elantra', 'sonata', 'tucson', 'santa fe', 'kona', 'palisade',
                                                  'ioniq 5', 'элантра', 'соната', 'туссан', 'санта фе']),
    'Kia': (['kia', 'киа', 'кіа'], ['optima', 'sorento', 'sportage', 'soul', 'forte', 'k5', 'telluride', 'niro', 'ev6',
                                    'оптима', 'соренто', 'спортейдж', 'соул']),
    'Mazda': (['mazda', 'мазда'], ['cx-5', 'cx-9', 'cx-30', 'cx-50', 'mazda 3', 'mazda 6', 'сх-5', 'сх5']),
    'Subaru': (['subaru', 'субару'], ['outback', 'forester', 'impreza', 'crosstrek', 'legacy', 'ascent', 'wrx',
                                      'аутбек', 'форестер', 'импреза', 'легаси']),
    'Volkswagen': (['volkswagen', 'vw', 'фольксваген'], ['jetta', 'passat', 'tiguan', 'atlas', 'golf', 'id.4', 'джетта',
                                                         'пассат', 'тигуан', 'атлас', 'гольф']),
    'Audi': (['audi', 'ауди', 'ауді'], ['a3', 'a4', 'a5', 'a6', 'q3', 'q5', 'q7', 'q8', 'e-tron']),
    'BMW': (['bmw', 'бмв'], ['x1', 'x3', 'x5', 'x6', 'x7', '3 series', '5 series', '330i', '530i', 'i3', 'i4']),
    'Mercedes': (['mercedes', 'mercedes-benz', 'мерседес'], ['c class', 'e class', 's class', 'gle', 'glc', 'gla', 'cla',
                                                             'c300', 'e350']),
    'Lexus': (['lexus', 'лексус'], ['rx', 'es', 'nx', 'gx', 'is', 'ux', 'rx350', 'rx450h', 'es350']),
    'Lincoln': (['lincoln', 'линкольн', 'лінкольн'], ['mkz', 'mkc', 'mkx', 'nautilus', 'aviator', 'navigator',
                                                      'corsair', 'continental']),
    'Acura': (['acura', 'акура'], ['mdx', 'rdx', 'tlx', 'ilx']),
    'Infiniti': (['infiniti', 'инфинити'], ['qx60', 'qx50', 'q50', 'qx80', 'qx55']),
    'Cadillac': (['cadillac', 'кадиллак'], ['escalade', 'xt4', 'xt5', 'xt6', 'ct5', 'эскалейд']),
    'Chrysler': (['chrysler', 'крайслер'], ['pacifica', '300', 'пацифика']),
    'Ram': (['ram', 'dodge ram', 'додж рам'], ['1500', '2500']),
    'GMC': (['gmc'], ['sierra', 'yukon', 'acadia', 'terrain']),
    'Mitsubishi': (['mitsubishi', 'мицубиси', 'міцубісі'], ['outlander', 'outlander phev', 'eclipse cross',
                                                            'аутлендер']),
    'Volvo': (['volvo', 'вольво'], ['xc40', 'xc60', 'xc90', 's60', 's90']),
    'Porsche': (['porsche', 'порше'], ['cayenne', 'macan', 'panamera', 'taycan', 'кайен', 'макан']),
    'Land Rover': (['land rover', 'ленд ровер'], ['range rover', 'range rover sport', 'range rover evoque', 'discovery',
                                                   'рендж ровер']),
}
JAPAN = {
    'Toyota': (['toyota', 'тойота'], ['prius', 'aqua', 'camry', 'crown', 'land cruiser', 'land cruiser prado', 'prado',
                                      'alphard', 'vellfire', 'harrier', 'rav4', 'corolla', 'corolla cross', 'c-hr',
                                      'yaris', 'yaris cross', 'noah', 'voxy', 'sienta', 'hiace', 'hilux', 'приус', 'аква',
                                      'камри', 'краун', 'ленд крузер', 'прадо', 'альфард', 'харриер', 'рав4', 'королла']),
    'Honda': (['honda', 'хонда'], ['fit', 'vezel', 'freed', 'stepwgn', 'cr-v', 'accord', 'odyssey', 'n-box', 'shuttle',
                                   'фит', 'везел', 'фрид', 'степвагон', 'срв']),
    'Nissan': (['nissan', 'ниссан', 'нісан'], ['leaf', 'note', 'note e-power', 'serena', 'x-trail', 'juke', 'qashqai',
                                               'elgrand', 'ariya', 'лиф', 'ноут', 'серена', 'икс трейл', 'х трейл', 'жук',
                                               'кашкай']),
    'Mazda': (['mazda', 'мазда'], ['cx-5', 'cx-30', 'cx-3', 'cx-8', 'cx-60', 'mazda 3', 'mazda 6', 'сх-5', 'сх5']),
    'Subaru': (['subaru', 'субару'], ['forester', 'outback', 'xv', 'impreza', 'levorg', 'legacy', 'форестер', 'аутбек',
                                      'импреза', 'леворг']),
    'Mitsubishi': (['mitsubishi', 'мицубиси', 'міцубісі'], ['outlander', 'outlander phev', 'pajero', 'pajero sport',
                                                            'delica', 'eclipse cross', 'аутлендер', 'паджеро', 'делика']),
    'Lexus': (['lexus', 'лексус'], ['rx', 'nx', 'es', 'lx', 'ux', 'is', 'gx', 'rx450h', 'nx300h', 'lx570']),
    'Suzuki': (['suzuki', 'сузуки'], ['jimny', 'swift', 'vitara', 'escudo', 'hustler', 'джимни', 'свифт', 'витара']),
    'Infiniti': (['infiniti', 'инфинити'], ['qx50', 'qx60', 'qx70', 'q50']),
    'Daihatsu': (['daihatsu', 'дайхатсу'], ['tanto', 'move', 'rocky']),
}
TEXT = {
    'usa': {'uk': ['{m} з сша', '{m} з америки', 'купити {m} з сша', '{m} з сша ціна', 'пригон {m} з сша',
                   '{m} з сша під ключ', '{m} з аукціону сша'],
            'ru': ['{m} из сша', '{m} с сша', '{m} из америки', 'купить {m} из сша', '{m} из сша цена',
                   'пригон {m} из сша', '{m} из сша под ключ', '{m} с аукциона сша'],
            'year_uk': ['{m} {y} з сша'], 'year_ru': ['{m} {y} из сша', '{m} {y} с сша'],
            'general_uk': ['авто з сша', 'авто з америки', 'машини з сша', 'автомобілі з сша', 'авто з сша під ключ',
                           'пригон авто з сша', 'замовити авто з сша', 'авто з аукціону сша', 'аукціони авто сша',
                           'авто з сша ціни', 'авто з сша київ', 'copart', 'копарт', 'iaai україна', 'manheim',
                           'електромобіль з сша', 'гібрид з сша', 'авто з сша під замовлення'],
            'general_ru': ['авто из сша', 'авто с сша', 'авто из америки', 'машины из сша', 'автомобили из сша',
                           'авто из сша под ключ', 'пригон авто из сша', 'заказать авто из сша', 'авто с аукциона сша',
                           'аукционы авто сша', 'авто из сша цены', 'авто из сша киев', 'копарт аукцион',
                           'электромобиль из сша', 'гибрид из сша', 'авто из сша под заказ'],
            'hub': ('UA — США під ключ', 'RU — США под ключ'), 'group': ('UA — США — ', 'RU — США — ')},
    'japan': {'uk': ['{m} з японії', 'купити {m} з японії', '{m} з японії ціна', 'пригон {m} з японії',
                     '{m} з японії під ключ', '{m} з аукціону японії'],
              'ru': ['{m} из японии', '{m} с японии', 'купить {m} из японии', '{m} из японии цена',
                     'пригон {m} из японии', '{m} из японии под ключ', '{m} с аукциона японии'],
              'year_uk': ['{m} {y} з японії'], 'year_ru': ['{m} {y} из японии', '{m} {y} с японии'],
              'general_uk': ['авто з японії', 'машини з японії', 'автомобілі з японії', 'авто з японії під ключ',
                             'пригон авто з японії', 'замовити авто з японії', 'авто з аукціону японії',
                             'аукціони авто японії', 'японські авто під замовлення', 'авто з японії ціни',
                             'авто з японії київ', 'гібрид з японії', 'авто з японії під замовлення'],
              'general_ru': ['авто из японии', 'авто с японии', 'машины из японии', 'автомобили из японии',
                             'авто из японии под ключ', 'пригон авто из японии', 'заказать авто из японии',
                             'авто с аукциона японии', 'аукционы авто японии', 'японские авто под заказ',
                             'авто из японии цены', 'авто из японии киев', 'гибрид из японии',
                             'авто из японии под заказ'],
              'hub': ('UA — Японія під ключ', 'RU — Япония под ключ'), 'group': ('UA — Японія — ', 'RU — Япония — ')},
}
BRANDS = {'usa': USA, 'japan': JAPAN}
YEARS = range(2012, 2026)


def names(brands, brand):
    """«brand model» in every spelling (Latin models with Latin brands, Cyrillic with Cyrillic), then the bare brand."""
    spellings, models = brands[brand]
    latin = [s for s in spellings if s.isascii()]
    cyr = [s for s in spellings if not s.isascii()] or latin
    found = []
    for model in models:
        found += ['%s %s' % (s, model) for s in (latin if model.isascii() else cyr)]
    return found + spellings


def plan(country):
    """{group name: [keyword]} in priority order (general, brands, then «model + year»), unique, valid for Google."""
    text, brands = TEXT[country], BRANDS[country]
    groups, seen = {}, set()

    def add(group, phrase):
        if phrase not in seen and len(phrase) <= 80 and len(phrase.split()) <= 10:
            seen.add(phrase)
            groups.setdefault(group, []).append(phrase)

    for i, lang in enumerate(('uk', 'ru')):
        for phrase in text['general_' + lang]:
            add(text['hub'][i], phrase)
    for brand in brands:
        for i, lang in enumerate(('uk', 'ru')):
            for name in names(brands, brand):
                for p in text[lang]:
                    add(text['group'][i] + brand, p.format(m=name))
    for brand in brands:
        for i, lang in enumerate(('uk', 'ru')):
            for name in names(brands, brand)[:-len(brands[brand][0])]:
                for year in YEARS:
                    for p in text['year_' + lang]:
                        add(text['group'][i] + brand + (' — роки' if lang == 'uk' else ' — годы'),
                            p.format(m=name, y=year))
    return groups


if __name__ == '__main__':
    for c in BRANDS:
        g = plan(c)
        print(c, sum(map(len, g.values())), 'keywords in', len(g), 'groups; max group', max(map(len, g.values())))
