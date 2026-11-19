"""Korea page day buttons: «Аукціонів немає» (KOREA-WEEKTILE-001, owner 2026-11-19): «If on Friday there are no
auctions, say so — not "lots will appear in 1–2 days" when lots are already listed for Monday».

A later weekday without lots says «Лоти з'являться за 1–2 дні» only when the auction schedule has an auction that day
(lots.json `schedule`, Monday .. Sunday, from the auction's search form) and no later day has lots yet; otherwise
«Аукціонів немає». Holidays, Saturday/Sunday and today stay as KOREA-HOLIDAYS-001 made them; a page that reads an
older lots.json without `schedule` decides by the later lots only. Every other byte of video/korea.html stays; each
edit must match exactly once.
"""
SOON = '"soon": ["Лоти з\'являться за 1–2 дні", "Лоты появятся за 1–2 дня", "ლოტები გამოჩნდება 1–2 დღეში"]'
NONE = ('Аукціонів немає', 'Аукционов нет', 'აუქციონები არ არის')
RETURN = 'return d>new Date(Date.now()+324e5).toISOString().slice(0,10).replace(/-/g,"/")?t("soon"):n(0)+" "+t("cars");}'
LOAD = 'lots=d.lots||[];days();'
HOL = 'var HOL={'


def edits():
    return (
        (SOON, SOON + ', "none": ["%s", "%s", "%s"]' % NONE),
        (RETURN, 'if(d<=new Date(Date.now()+324e5).toISOString().slice(0,10).replace(/-/g,"/"))return n(0)+" "+t("cars");'
                 # soon: the schedule has an auction that weekday (Monday first) and no later day is listed yet
                 'var later=Object.keys(c).some(function(x){return x>d;}),plan=!SCH||(SCH[(w+6)%7]||[]).length>0;'
                 'return plan&&!later?t("soon"):t("none");}'),
        (LOAD, 'lots=d.lots||[];SCH=d.schedule||null;days();'),
        (HOL, 'var SCH=null;' + HOL),
    )


CHECK = 't("none")'  # public proof that this release is live


def build(source):
    text = source.decode('utf-8')
    if CHECK in text or any(text.count(old) != 1 for old, _ in edits()):
        raise ValueError('DAY_NONE_ANCHOR')
    for old, new in edits():
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
