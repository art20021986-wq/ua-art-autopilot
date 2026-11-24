"""Korea page day buttons: a day without auction lots says why (KOREA-HOLIDAYS-001, owner 2026-11-17).

Instead of «0 авто»: a public holiday of Korea — its name (korea_holidays.HOLIDAYS, uk/ru/ka); Saturday or Sunday —
«Вихідний»; a later working day — «Лоти з'являться за 1–2 дні» (the auction lists lots one or two days ahead; owner «2. Да»).
Today without lots keeps «0 авто» (there is no auction today). A day with lots keeps its car count. Only the day buttons change; every other
byte of video/korea.html stays; each edit must match exactly once.
"""
import json

import korea_holidays

LABEL = '"days": ["Усі дні", "Все дни", "ყველა დღე"]'
DAYOFF = ('Вихідний', 'Выходной', 'დასვენების დღე')
SOON = ("Лоти з'являться за 1–2 дні", 'Лоты появятся за 1–2 дня', 'ლოტები გამოჩნდება 1–2 დღეში')
COUNT = '"<small>"+n(c[d])+" "+t("cars")+"</small></button>";}).join("");}'
DAYS = 'function days(){'


def _table():
    """HOL = {'YYYY/MM/DD': [uk, ru, ka]} for the page script."""
    return json.dumps({day: list(names) for day, names in sorted(korea_holidays.HOLIDAYS.items())},
                      ensure_ascii=False, separators=(',', ':'))


def edits():
    return (
        (LABEL, LABEL + ', "dayoff": ["%s", "%s", "%s"], "soon": ["%s", "%s", "%s"]' % (DAYOFF + SOON)),
        (COUNT, '"<small>"+reason(d,c)+"</small></button>";}).join("");}'),
        (DAYS, 'var HOL=' + _table() + ';'
               # reason(day, cars per day): the car count, else the holiday name, else «Вихідний» on Sat/Sun, else
               # «Лоти з'являться…» for a later working day (today in Korea, UTC+9, keeps 0)
               'function reason(d,c){if(c[d])return n(c[d])+" "+t("cars");var h=HOL[d];'
               'if(h)return tri(function(i){return h[i];});'
               'var w=new Date(d.replace(/\\//g,"-")+"T00:00:00Z").getUTCDay();'
               'if(w===0||w===6)return t("dayoff");'
               'return d>new Date(Date.now()+324e5).toISOString().slice(0,10).replace(/-/g,"/")?t("soon"):n(0)+" "+t("cars");}'
               + DAYS),
    )


# Public proof that this release is live.
CHECK = 'function reason(d,c){'


def build(source):
    text = source.decode('utf-8')
    if CHECK in text or any(text.count(old) != 1 for old, _ in edits()):
        raise ValueError('DAY_REASON_ANCHOR')
    for old, new in edits():
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
