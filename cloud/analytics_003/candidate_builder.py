"""Build the analytics release 3 candidate from the exact installed sources (owner «Да» 2026-11-12, option 1 instead of
Microsoft Clarity).

analitika_yadro: the page script also reports photo clicks, other button/link clicks (their label only) and how far a
page was read (middle, end); the server accepts the three new event types; read depth is not a route step.
analitika_otchet: «Кнопка «…»» in «ЧТО НАЖИМАЛИ» and the new block «📜 СТРАНИЦЫ: ДОЧИТАЛИ И НАЖИМАЛИ» (ua_page_depth).
"""
import hashlib
from pathlib import Path

from release_constants import NEW_MODULES, PATCHED_MODULES

HERE = Path(__file__).resolve().parent
SOURCE_SHA256 = {
    # Installed now (ANALYTICS-AUDIT-PROBE-20261112 read them; fixtures/ are byte-exact copies).
    'analitika_yadro.py': '1c62f8d1cca21a786afecc34b79581104beb7378011159d704f219a9936875bd',
    'analitika_otchet.py': 'c24420dba766eda947d18d7be36e37dc91693be3cebc0e663eb55c7278c36df0',
}
SOURCE_FILES = tuple(SOURCE_SHA256)
DEPENDENCY_SHA256 = {}
MARK = 'UA-PAGE-DEPTH-001'
YADRO_CLICK = """  if(t2.indexOf('купить')>=0 || t2.indexOf('заброн')>=0 || t2.indexOf('вопрос')>=0 || t2.indexOf('заявк')>=0){ shlyom('cta',txt); return; }
"""
YADRO_PLAY = """document.addEventListener('play', function(ev){
  if(ev.target && ev.target.tagName==='VIDEO'){ shlyom('video',''); }
}, true);
"""
PATCHES = {
    'analitika_yadro.py': (
        ('                  "finance"])  # FINANCE-001: a visit to a finance partner\n',
         '                  "finance", "foto", "knopka", "scroll"])  # FINANCE-001: a visit to a finance partner; '
         + MARK + '\n'),
        ('                "finance": "Кредиты и лизинг"}\n',
         '                "finance": "Кредиты и лизинг", "foto": "Фото", "knopka": "Кнопка"}  # ' + MARK + '\n'),
        ('    shag = nazvanie_stranicy(put) if tip in ("page", "card", "diag") else _imya_tipa(tip)\n',
         '    if tip == "scroll":  # ' + MARK + ': read depth is not a route step\n'
         '        c.execute("UPDATE sessions SET konec=? WHERE sid=?", (ts, sid))\n'
         '        d.commit()\n'
         '        d.close()\n'
         '        return "ok"\n'
         '    shag = nazvanie_stranicy(put) if tip in ("page", "card", "diag") else _imya_tipa(tip)\n'),
        (YADRO_CLICK,
         YADRO_CLICK +
         "  var el=ev.target; // " + MARK + ": photos and every other button or link (label only)\n"
         "  if(el && el.tagName==='IMG'){ shlyom('foto',''); return; }\n"
         "  var b=(a && a.tagName==='A') ? a : (el && el.closest ? el.closest('button,[role=button]') : null);\n"
         "  if(b){ shlyom('knopka',((b.textContent||'').replace(/\\s+/g,' ').trim() || b.getAttribute('aria-label') || '').slice(0,40)); }\n"),
        (YADRO_PLAY,
         YADRO_PLAY +
         "var glub={}, tm=0; // " + MARK + ": the page was read to the middle / to the end\n"
         "function glubina(){\n"
         "  var d=document.documentElement, vys=Math.max(d.scrollHeight, document.body ? document.body.scrollHeight : 0);\n"
         "  if(!vys){ return; }\n"
         "  var pr=((window.pageYOffset||d.scrollTop||0)+window.innerHeight)*100/vys;\n"
         "  if(pr>=50 && !glub[50]){ glub[50]=1; shlyom('scroll','50'); }\n"
         "  if(pr>=95 && !glub[100]){ glub[100]=1; shlyom('scroll','100'); }\n"
         "}\n"
         "window.addEventListener('scroll', function(){ if(tm){ return; } tm=setTimeout(function(){ tm=0; glubina(); }, 400); }, {passive:true});\n"
         "setTimeout(glubina, 1500);\n"),
    ),
    'analitika_otchet.py': (
        ('SISTEMNYE = ("start", "init", "ping", "heartbeat", "session_start")\n',
         'SISTEMNYE = ("start", "init", "ping", "heartbeat", "session_start", "scroll")  # ' + MARK + '\n'),
        ('    ("bron", "Бронь"), ("zayavka", "Заявка"),\n]\n',
         '    ("bron", "Бронь"), ("zayavka", "Заявка"), ("foto", "Фото"),  # ' + MARK + '\n]\n'),
        ('def klass_istochnika(istochnik, referrer, utm_source):\n',
         'def imya_sobytiya(s, mashiny):  # ' + MARK + ': a button is shown with its label\n'
         '    tip = (s["tip"] or "").lower()\n'
         '    if tip == "knopka":\n'
         '        return "Кнопка «%s»" % ((s.get("z") or "").strip()[:40] or "без надписи")\n'
         '    return imya_deystviya(tip, s["adres"], mashiny)\n'
         '\n'
         '\n'
         'def klass_istochnika(istochnik, referrer, utm_source):\n'),
        ('    polya = [E["vremya"], E["tip"], E["stranica"], E["posetitel"], E["sessiya"]]\n',
         '    polya = [E["vremya"], E["tip"], E["stranica"], E["posetitel"], E["sessiya"], "znachenie"]  # ' + MARK + '\n'),
        ('            "sess": (d.get(E["sessiya"]) or "") if E["sessiya"] else "",\n',
         '            "sess": (d.get(E["sessiya"]) or "") if E["sessiya"] else "",\n'
         '            "z": d.get("znachenie") or "",\n'),
        ('        deystvie = imya_deystviya(tip, s["adres"], mashiny)\n',
         '        deystvie = imya_sobytiya(s, mashiny)\n'),
        ('    if avto_prosmotry:\n',
         '    try:  # ' + MARK + ': pages read to the middle / end and what was clicked there\n'
         '        import ua_page_depth\n'
         '        stroki.extend(ua_page_depth.stroki(sobytiya, lambda adres: imya_stranicy(adres, mashiny),\n'
         '                                           lambda s: imya_sobytiya(s, mashiny), SISTEMNYE))\n'
         '    except Exception:\n'
         '        pass\n'
         '\n'
         '    if avto_prosmotry:\n'),
    ),
}


def page_paths(root):
    """No public page changes in this release."""
    return []


def patch(name, value):
    if MARK.encode() in value:
        raise ValueError('ALREADY_PATCHED:' + name)
    for old, new in PATCHES[name]:
        old, new = old.encode(), new.encode()
        if value.count(old) != 1:
            raise ValueError('PATCH_ANCHOR:%s:%d' % (name, value.count(old)))
        value = value.replace(old, new)
    return value


def build(source, pages):
    for name, digest in SOURCE_SHA256.items():
        value = source.get(name)
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: (HERE / name).read_bytes() for name in NEW_MODULES}
    for name in PATCHED_MODULES:
        result[name] = patch(name, source[name])
    return result
