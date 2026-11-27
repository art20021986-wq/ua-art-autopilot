"""Korea page day buttons: a coming day shows its auctions and their start in Kyiv time (KOREA-PLAN-DAYS-001,
owner 2026-11-26 «Да»: as on the home tile, not «Лоти з'являться за 1–2 дні»).

The collector publishes lots.json `planned` ({'YYYY/MM/DD': [{'name', 'start'?}]}, the tile's coming days without
lots: houses from the auction schedule and the houses seen on that weekday). A coming day with `planned` houses and
no later day listed shows them, one per line («AutoPlus · старт 05:00 Київ»); without `planned` (an older list) the
button keeps «Лоти з'являться».
Every other byte of video/korea.html stays; each edit must match exactly once.
"""
SOON_RETURN = 'return plan&&!later?t("soon"):t("none");}'
LOAD = 'SCH=d.schedule||null;days();'
DECL = 'var SCH=null;'
CSS = '.kl-day small{opacity:.8;font-size:12px}'


def edits():
    return (
        (SOON_RETURN, 'var p=PLAN&&PLAN[d];if(p&&p.length&&!later)return p.map(function(h){'
                      'return \'<span class="kl-plan">\'+tri(function(i){var k=h.start?kyiv(h.start):"";'
                      'return h.name+(k?" · "+ST[i]+" "+k+" "+ZN[i][1]:"");})+"</span>";}).join("");' + SOON_RETURN),
        (LOAD, 'SCH=d.schedule||null;PLAN=d.planned||null;days();'),
        (DECL, 'var SCH=null,PLAN=null,ST=["старт","старт","დაწყება"];'),
        (CSS, CSS + '.kl-plan{display:block;white-space:nowrap}'),
    )


CHECK = 'PLAN=d.planned||null'  # public proof that this release is live


def build(source):
    text = source.decode('utf-8')
    if CHECK in text or any(text.count(old) != 1 for old, _ in edits()):
        raise ValueError('PLAN_DAYS_ANCHOR')
    for old, new in edits():
        text = text.replace(old, new, 1)
    return text.encode('utf-8')
