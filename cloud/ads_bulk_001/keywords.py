"""Buyer searches for the Kyiv campaign, generated (owner 2026-11-26 via the coordinator: «сделай мне поисковых запросов
5000 … все, что связано непосредственно с автомобилями … на украинском и русском языке параллельно, кто как вбивает»).

Pure: no network. Every brand and model sold at the Korean car auctions (Hyundai, Kia, Genesis, Chevrolet / GM Korea,
Renault Korea / Samsung, SsangYong / KGM, and the imports there) × buyer phrasings, Ukrainian and Russian, Latin and
Cyrillic spellings as people type them. One group per brand and language; the five models with their own page keep
their groups. PER_DAY is the default night (Explorer API level: about 2 880 operations a day); a run may carry its own
limit (source_remote --limit, Basic access).
"""
BRANDS = {
    'Hyundai': (['hyundai', 'хюндай', 'хендай', 'хундай', 'хьюндай'],
                ['sonata', 'avante', 'elantra', 'grandeur', 'tucson', 'santa fe', 'palisade', 'kona', 'venue', 'casper',
                 'staria', 'starex', 'ioniq 5', 'ioniq 6', 'ioniq', 'veloster', 'i30', 'i40', 'porter', 'nexo',
                 'maxcruz', 'соната', 'аванте', 'грандеур', 'туссан', 'туксон', 'санта фе', 'палисад', 'кона', 'старекс',
                 'стария', 'портер', 'иониq 5']),
    'Kia': (['kia', 'киа', 'кіа'],
            ['k3', 'k5', 'k7', 'k8', 'k9', 'morning', 'ray', 'sportage', 'sorento', 'carnival', 'seltos', 'niro', 'mohave',
             'stinger', 'soul', 'ev6', 'ev9', 'stonic', 'bongo', 'carens', 'к5', 'к7', 'к8', 'спортейдж', 'соренто',
             'карнивал', 'селтос', 'ниро', 'мохаве', 'стингер', 'морнинг']),
    'Genesis': (['genesis', 'генезис', 'дженезис'], ['g70', 'g80', 'g90', 'gv60', 'gv70', 'gv80']),
    'Chevrolet': (['chevrolet', 'шевроле'], ['spark', 'malibu', 'trax', 'trailblazer', 'equinox', 'cruze', 'orlando',
                                            'captiva', 'traverse', 'colorado', 'bolt', 'малибу', 'спарк', 'каптива']),
    'Renault Samsung': (['renault samsung', 'renault korea', 'samsung', 'рено самсунг', 'самсунг'],
                        ['sm3', 'sm5', 'sm6', 'sm7', 'qm3', 'qm5', 'qm6', 'xm3', 'arkana']),
    'SsangYong': (['ssangyong', 'kgm', 'ссангйонг', 'санг енг', 'санйонг'],
                  ['tivoli', 'korando', 'rexton', 'musso', 'torres', 'actyon', 'тиволи', 'корандо', 'рекстон', 'торрес']),
    'Mercedes': (['mercedes', 'mercedes-benz', 'мерседес'],
                 ['e class', 'c class', 's class', 'b class', 'glc', 'gle', 'gla', 'cla', 'e220', 'e300', 'c200', 'е класс']),
    'BMW': (['bmw', 'бмв'], ['3 series', '5 series', '7 series', 'x3', 'x5', 'x6', '320d', '520d', '530i', 'x4', 'x7']),
    'Audi': (['audi', 'ауди', 'ауді'], ['a4', 'a6', 'a8', 'q5', 'q7', 'q8', 'a5', 'q3', 'e-tron']),
    'Volkswagen': (['volkswagen', 'фольксваген'], ['tiguan', 'passat', 'arteon', 'тигуан', 'пассат']),
    'Lexus': (['lexus', 'лексус'], ['es', 'rx', 'nx', 'es300h']),
    'Toyota': (['toyota', 'тойота'], ['camry', 'rav4', 'камри']),
    'Volvo': (['volvo', 'вольво'], ['xc60', 'xc90', 's90']),
    'Tesla': (['tesla', 'тесла'], ['model 3', 'model y']),
    'Porsche': (['porsche', 'порше'], ['cayenne', 'macan', 'panamera', 'кайен', 'макан']),
    'Land Rover': (['land rover', 'ленд ровер'], ['range rover', 'discovery', 'рендж ровер']),
}
UK = ['{m} з кореї', 'купити {m} з кореї', '{m} з кореї ціна', '{m} під замовлення', 'пригон {m} з кореї',
      '{m} з кореї під ключ']
RU = ['{m} из кореи', '{m} с кореи', 'купить {m} из кореи', '{m} из кореи цена', '{m} под заказ',
      'пригон {m} из кореи', '{m} из кореи под ключ']
GENERAL_UK = ['авто з кореї', 'машини з кореї', 'автомобілі з кореї', 'авто з кореї під ключ', 'пригон авто з кореї',
              'замовити авто з кореї', 'авто з аукціону кореї', 'корейські авто під замовлення', 'авто з кореї київ',
              'авто з кореї ціни', 'автоаукціон корея', 'аукціони авто кореї', 'авто з кореї на газу',
              'авто з кореї lpi', 'авто з кореї дизель', 'електромобіль з кореї', 'гібрид з кореї']
GENERAL_RU = ['авто из кореи', 'авто с кореи', 'машины из кореи', 'машины с кореи', 'автомобили из кореи',
              'авто из кореи под ключ', 'пригон авто из кореи', 'заказать авто из кореи', 'авто с аукциона кореи',
              'корейские авто под заказ', 'авто из кореи киев', 'авто из кореи цены', 'автоаукцион корея',
              'аукционы авто кореи', 'авто из кореи на газу', 'авто из кореи lpi', 'авто из кореи дизель',
              'электромобиль из кореи', 'гибрид из кореи', 'энкар', 'encar авто']
# The five models with their own pages keep their groups (name -> model words found in a phrase).
MODEL_GROUPS = {'Kia K5': ('k5', 'к5'), 'Hyundai Sonata': ('sonata', 'соната'), 'Hyundai Tucson': ('tucson', 'туссан', 'туксон'),
                'Kia Sportage': ('sportage', 'спортейдж'), 'Hyundai Santa Fe': ('santa fe', 'санта фе')}
NEGATIVE_MORE = ['шрот', 'прокат', 'диски', 'расход', 'витрата', 'масло', 'аккумулятор', 'акумулятор', 'фары', 'фари',
                 'бампер', 'двигатель', 'двигун', 'коробка передач', 'кпп', 'страховка', 'страхування', 'такси', 'таксі',
                 'машинка', 'мультик', 'раскраска', 'гта', 'gta', 'симулятор', 'обои', 'шпалери', 'чехлы', 'коврики',
                 'розборка', 'разборка', 'запчастини', 'запчасти', 'аватр', 'avatr']
PER_DAY = 2400
# Owner 2026-11-26 (via the coordinator, «Все да»): as many narrow «model + year from Korea» searches as possible — few
# searches each, but real buyers. Phrase match also catches «купити … під ключ», «… під замовлення», «… ціна» around it.
YEARS = range(2012, 2026)
YEAR_UK = ['{m} {y} з кореї']
YEAR_RU = ['{m} {y} из кореи', '{m} {y} с кореи']
AUCTION = {'uk': 'UA — Аукціон — ', 'ru': 'RU — Аукцион — '}


def names(brand):
    """«brand model» in every spelling, then the bare brand."""
    spellings, models = BRANDS[brand]
    latin = [s for s in spellings if s.isascii()]
    found = []
    for model in models:
        pool = latin if model.isascii() else [s for s in spellings if not s.isascii()] or latin
        found += ['%s %s' % (s, model) for s in pool]
    return found + spellings


def phrases(lang, brand):
    pattern = UK if lang == 'uk' else RU
    return [p.format(m=n) for n in names(brand) for p in pattern]


OTHER = ('Volkswagen', 'Lexus', 'Toyota', 'Volvo', 'Tesla', 'Porsche', 'Land Rover')


def group_of(lang, brand, phrase):
    prefix = 'UA — ' if lang == 'uk' else 'RU — '
    if brand in OTHER:
        return prefix + ('Інші марки з Кореї' if lang == 'uk' else 'Другие марки из Кореи')
    if brand in ('Hyundai', 'Kia'):
        padded = ' %s ' % phrase
        for model, words in MODEL_GROUPS.items():
            if model.startswith(brand) and any(' %s ' % w in padded for w in words):
                return prefix + model
    return prefix + brand


def plan():
    """{group name: [keyword]} in priority order (general, then brands), unique, valid for Google."""
    groups = {}
    seen = set()
    for lang, general in (('uk', GENERAL_UK), ('ru', GENERAL_RU)):
        key = 'UA — Корея під ключ' if lang == 'uk' else 'RU — Корея под ключ'
        for phrase in general:
            if phrase not in seen:
                seen.add(phrase)
                groups.setdefault(key, []).append(phrase)
    for brand in BRANDS:
        for lang in ('uk', 'ru'):
            for phrase in phrases(lang, brand):
                if phrase in seen or len(phrase) > 80 or len(phrase.split()) > 10:
                    continue
                seen.add(phrase)
                groups.setdefault(group_of(lang, brand, phrase), []).append(phrase)
    for brand in BRANDS:
        for lang, pattern in (('uk', YEAR_UK), ('ru', YEAR_RU)):
            for name in names(brand):
                for year in YEARS:
                    for p in pattern:
                        phrase = p.format(m=name, y=year)
                        if phrase in seen or len(phrase) > 80 or len(phrase.split()) > 10:
                            continue
                        seen.add(phrase)
                        groups.setdefault(AUCTION[lang] + brand, []).append(phrase)
    return groups


def today(have=frozenset(), limit=PER_DAY, groups=None):
    """The next part: up to limit keywords not yet in the campaign, round-robin over groups so every group gets some
    (groups: another plan, e.g. the USA one; default the Korea plan)."""
    queue = {g: [k for k in words if (g, k) not in have] for g, words in (plan() if groups is None else groups).items()}
    picked = []
    while len(picked) < limit and any(queue.values()):
        for g in list(queue):
            if queue[g] and len(picked) < limit:
                picked.append((g, queue[g].pop(0)))
    return picked


def split(left_korea, left_usa, total=None):
    """Tonight's part for each campaign (owner 28.11 «да»): half each; a country with less left gives the rest to the
    other, so the night stays within total (the run's limit, default PER_DAY)."""
    total = PER_DAY if total is None else total
    korea = min(left_korea, max(total // 2, total - left_usa))
    return korea, min(left_usa, total - korea)
