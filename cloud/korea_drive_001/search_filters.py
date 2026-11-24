"""Korea page lot search: fuel, year from/to and mileage as lists (KOREA-DRIVE-001 package, owner 2026-11-17).

- «Паливо»: «Будь-яке» + only the fuels the lot list has (lots.json `fuel` keys), in the engine row's own words;
- «Рік від» / «Рік до»: native lists of the years the lot list has, oldest first, + «Будь-який»; a «від» later than
  «до» swaps the two so the list never goes empty without a reason;
- «Колір»: «Будь-який» + only the colour families the lot list has (lots.json `color`, korea_auction/color.py), in the
  lot window's own words (lot_rows.COLOR_WORDS), «Інший» last;
- «Пробіг до, км»: a native list (steps from the lot list mileages 17.11: median 129 000, 90 % under 230 000 km).
Native <select>: a phone opens its own picker. Works with the other filters and the sort. Every other byte of
video/korea.html stays; each edit must match exactly once.
"""
KM_STEPS = (30000, 50000, 75000, 100000, 150000, 200000, 250000, 300000)
FUELS = ('gasoline', 'diesel', 'hybrid', 'lpg', 'electric', 'hydrogen')  # the engine row keys (KOREA-ENGINE-001)
COLORS = ('white', 'black', 'gray', 'silver', 'blue', 'red', 'brown', 'beige', 'green', 'yellow', 'orange', 'other')
WORDS = (('any', 'Будь-який', 'Любой', 'ნებისმიერი'),)


def _label(uk, ru, ka, control):
    return ('<label><span data-uk="%s" data-ru="%s" data-ka="%s">%s</span>%s</label>' % (uk, ru, ka, uk, control))


YEAR_FROM = ('<label><span data-uk="Рік від" data-ru="Год от" data-ka="წელი დან">Рік від</span>'
             '<input id="kl-year" type="number" inputmode="numeric"></label>')
KM = ('<label><span data-uk="Пробіг до, км" data-ru="Пробег до, км" data-ka="გარბენი მდე, კმ">Пробіг до, км</span>'
      '<input id="kl-km" type="number" inputmode="numeric"></label>')
MODEL_END = '<select id="kl-model"></select></label>'
L_END = '"cars": ["авто", "авто", "ავტო"]}'
FILTER = ('function filter(){var m=$("kl-maker").value,md=$("kl-model").value,y=+$("kl-year").value||0,'
          'km=+$("kl-km").value||0,')
MATCH = '&&l.year>=y&&(!km||l.mileage_km<=km)'
LISTEN = '["kl-year","kl-km","kl-usd","kl-sort","kl-model"].forEach'
LOADED = 'opt($("kl-maker"),uniq(lots.map(function(l){return l.maker;})));'
LISTS = (
    # pick(sel, [[value, uk, ru, ka], ...]): a list whose first option is «Будь-який»; the chosen value is kept
    'function pick(sel,items){var keep=sel.value;sel.innerHTML="";[["",L.any[0],L.any[1],L.any[2]]].concat(items)'
    '.forEach(function(v){var o=document.createElement("option");o.value=v[0];o.textContent=v[1];'
    'o.setAttribute("data-uk",v[1]);o.setAttribute("data-ru",v[2]);o.setAttribute("data-ka",v[3]);sel.appendChild(o);});'
    'sel.value=keep;if(sel.selectedIndex<0)sel.value="";}'
    # words of the lot window rows, with a capital letter in the lists («бензин» -> «Бензин»)
    'function cap(w){return w.map(function(x){return x.charAt(0).toUpperCase()+x.slice(1);});}'
    'function have(key,values){return values.filter(function(v){return lots.some(function(l){return l[key]===v;});});}'
    'function lists(){var ys=uniq(lots.map(function(l){return String(l.year);}));'
    'ys=ys.map(function(y){return [y,y,y,y];});pick($("kl-year"),ys);pick($("kl-year-to"),ys);'
    'pick($("kl-km"),KMS.map(function(k){return [String(k),n(k),n(k),n(k)];}));'
    'pick($("kl-fuel"),have("fuel",FUELS).map(function(f){return [f].concat(cap(L["fuel_"+f]));}));'
    'pick($("kl-color"),have("color",COLORS).map(function(c){return [c].concat(cap(L["color_"+c]));}));}'
    'function years(){var a=$("kl-year"),b=$("kl-year-to");if(a.value&&b.value&&+a.value>+b.value){'
    'var v=a.value;a.value=b.value;b.value=v;}}'
)
EDITS = (
    (YEAR_FROM,
     YEAR_FROM.replace('<input id="kl-year" type="number" inputmode="numeric">', '<select id="kl-year"></select>')
     + _label('Рік до', 'Год до', 'წელი მდე', '<select id="kl-year-to"></select>')),
    (KM, KM.replace('<input id="kl-km" type="number" inputmode="numeric">', '<select id="kl-km"></select>')),
    (MODEL_END, MODEL_END + _label('Паливо', 'Топливо', 'საწვავი', '<select id="kl-fuel"></select>')
     + _label('Колір', 'Цвет', 'ფერი', '<select id="kl-color"></select>')),
    (L_END, L_END[:-1] + ''.join(', "%s": ["%s", "%s", "%s"]' % item for item in WORDS) + '}'
     + ',KMS=[%s],FUELS=[%s],COLORS=[%s]' % (','.join(str(k) for k in KM_STEPS), ','.join('"%s"' % f for f in FUELS),
                                           ','.join('"%s"' % c for c in COLORS))),
    (FILTER, FILTER + 'yt=+$("kl-year-to").value||0,fu=$("kl-fuel").value,co=$("kl-color").value,'),
    (MATCH, MATCH + '&&(!yt||l.year<=yt)&&(!fu||l.fuel===fu)&&(!co||l.color===co)'),
    (LISTEN, '$("kl-year").addEventListener("change",years);$("kl-year-to").addEventListener("change",years);'
             '["kl-year","kl-year-to","kl-km","kl-fuel","kl-color","kl-usd","kl-sort","kl-model"].forEach'),
    (LOADED, LOADED + 'lists();'),
    ('function filter(){', LISTS + 'function filter(){'),
)
# Public proof that this release is live.
CHECK = 'id="kl-year-to"'


def build(source):
    text = source.decode('utf-8')
    if CHECK in text or any(text.count(old) != 1 for old, _ in EDITS):
        raise ValueError('SEARCH_FILTERS_ANCHOR')
    for old, new in EDITS:
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
