"""KOREA-TIME-001 page edits (owner 2026-11-12): the auction start in Korea time and Kyiv time on the auction cards.

Pages as KOREA-LOTS-FULL-001 installs them (cloud/korea_lots_full_001: ua_korea_lots.py, edit_order.py):
- video/korea.html lot list: the list card stamp «чт, 18.11 · 12:00» and the lot card «середа, 18 листопада, 12:00»
  get « Корея · 05:00 Київ»; the label «Початок торгів (час Кореї)» loses «(час Кореї)».
- video/order/order.js model carousels: the lot strip «Аукціон 18.11 · AA» becomes «Аукціон 18.11 · 12:00 Корея ·
  05:00 Київ · AA» (order-strings.json gets the two words; podbor.html loads the new order.js version, which also
  reloads the strings).
Kyiv time is worked out in the visitor's browser (Intl, Europe/Kyiv, summer time included; the Kyiv day is added when
it differs); without it the Korea time alone. Small exact edits: each original fragment must occur exactly once and a
page that already has the edit is refused.
"""
import re

KOREA = 'video/korea.html'
PODBOR = 'video/podbor.html'
ORDER = 'video/order/order.js'
STRINGS = 'video/order/order-strings.json'
FILES = (KOREA, ORDER, PODBOR, STRINGS)
VERSION = '20261112.71'  # order.js (and its strings) asset version on the order page

KOREA_EDITS = (
    ('"start": ["Початок торгів (час Кореї)", "Начало торгов (время Кореи)", "ვაჭრობის დაწყება (კორეის დრო)"]',
     '"start": ["Початок торгів", "Начало торгов", "ვაჭრობის დაწყება"]'),
    ('+" · "+String(s).slice(11,16);});}', '+" · "+String(s).slice(11,16)+zones(s,i);});}'),
    ('+", "+String(l.auction_start).slice(11,16);}))', '+", "+String(l.auction_start).slice(11,16)+zones(l.auction_start,i);}))'),
    # kyiv('YYYY/MM/DD HH:MM' Korea, UTC+9) -> '05:00' / '23:00 (17.11)' / '' (no Intl); zones(s, language) ->
    # ' Корея · 05:00 Київ' (plain text: tri() escapes it)
    ('function tri(f){',
     'var ZN=[["Корея","Київ"],["Корея","Киев"],["კორეა","კიევი"]];'
     'function kyiv(s){var m=/^(\\d{4})\\/(\\d\\d)\\/(\\d\\d) (\\d\\d:\\d\\d)/.exec(s||""),p=null;if(!m)return "";'
     'var at=new Date(m[1]+"-"+m[2]+"-"+m[3]+"T"+m[4]+":00+09:00");'
     '["Europe/Kyiv","Europe/Kiev"].some(function(z){try{p={};new Intl.DateTimeFormat("en-GB",{timeZone:z,'
     'day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit",hour12:false}).formatToParts(at)'
     '.forEach(function(x){p[x.type]=x.value;});return true;}catch(e){p=null;return false;}});'
     'if(!p||!p.hour)return "";var d=p.day+"."+p.month;'
     'return (p.hour==="24"?"00":p.hour)+":"+p.minute+(d===m[3]+"."+m[2]?"":" ("+d+")");}'
     'function zones(s,i){var k=kyiv(s);return " "+ZN[i][0]+(k?" · "+k+" "+ZN[i][1]:"");}'
     'function tri(f){'),
)
ORDER_EDITS = (
    ("function auctionSlides(key) {\n",
     "// KOREA-TIME-001: ' · 12:00 Корея · 05:00 Київ' for a lot start 'YYYY/MM/DD HH:MM' (Korea time, UTC+9).\n"
     "function auctionTime(start) {\n"
     "  const m=/^(\\d{4})\\/(\\d\\d)\\/(\\d\\d) (\\d\\d:\\d\\d)/.exec(start||'');\n"
     "  if(!m) return '';\n"
     "  const at=new Date(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:00+09:00`);\n"
     "  for(const zone of ['Europe/Kyiv','Europe/Kiev']) {\n"
     "    try {\n"
     "      const p=Object.fromEntries(new Intl.DateTimeFormat('en-GB',{timeZone:zone,day:'2-digit',month:'2-digit',"
     "hour:'2-digit',minute:'2-digit',hour12:false}).formatToParts(at).map(x=>[x.type,x.value]));\n"
     "      const day=`${p.day}.${p.month}`;\n"
     "      return ` · ${m[4]} ${t('auction_korea')} · ${p.hour==='24'?'00':p.hour}:${p.minute}`"
     "+(day===`${m[3]}.${m[2]}`?'':` (${day})`)+` ${t('auction_kyiv')}`;\n"
     "    } catch(error) {}\n"
     "  }\n"
     "  return ` · ${m[4]} ${t('auction_korea')}`;\n"
     "}\n"
     "function auctionSlides(key) {\n"),
    ("    `${t('auction_lot')} ${lot.date}`+(lot.score?` · ${lot.score}`:''),\n",
     "    `${t('auction_lot')} ${lot.date}`+auctionTime(lot.start)+(lot.score?` · ${lot.score}`:''),\n"),
)
STRINGS_EDITS = tuple((old, old + ' ' + new) for old, new in (
    ('"auction_lot": "Аукціон",', '"auction_korea": "Корея", "auction_kyiv": "Київ",'),
    ('"auction_lot": "Аукцион",', '"auction_korea": "Корея", "auction_kyiv": "Киев",'),
    ('"auction_lot": "აუქციონი",', '"auction_korea": "კორეა", "auction_kyiv": "კიევი",'),
))
EDITS = {KOREA: KOREA_EDITS, ORDER: ORDER_EDITS, STRINGS: STRINGS_EDITS}
APPLIED = {KOREA: 'function kyiv(', ORDER: 'function auctionTime(', STRINGS: '"auction_kyiv"',
           PODBOR: 'order/order.js?v=' + VERSION}
SCRIPT_TAG = re.compile(r'order/order\.js\?v=[0-9.]+')


def build(name, text):
    """One live file (text) with this release applied."""
    if APPLIED[name] in text:
        raise ValueError('KOREA_TIME_ALREADY_APPLIED:' + name)
    if name == PODBOR:
        if len(SCRIPT_TAG.findall(text)) != 1:
            raise ValueError('KOREA_TIME_FRAGMENT_NOT_UNIQUE:' + name)
        return SCRIPT_TAG.sub('order/order.js?v=' + VERSION, text)
    for old, new in EDITS[name]:
        if text.count(old) != 1:
            raise ValueError('KOREA_TIME_FRAGMENT_NOT_UNIQUE:%s:%s' % (name, old[:24]))
        text = text.replace(old, new)
    return text
