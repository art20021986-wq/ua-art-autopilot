"""Build the «Посетители из Украины» candidate (owner «да» 2026-11-26: «Один, да, второй, да» — the button in «📊 Аналитика»,
the screen as in the mock-up, the daily summary at 09:00 Kyiv; earlier «да» to the counter items 1–3).

- ua_visitors_ua.py (new): the report, read-only over analytics.db.
- ua_visitors_bot.py (new): the screens, the custom period message, the 09:00 job.
- analitika_yadro.py: the page script sends the browser time zone, language and device type (no IP), names Google Ads
  clicks «Реклама Google» (gclid / gbraid / wbraid), and sends nothing from a device opened once with ?ua_staff=1
  (?ua_staff=0 undoes it); the sessions table keeps tz, lg, dv (columns added if missing).
- analitika_knopka.py: one row «🇺🇦 Посетители из Украины» in «📊 Аналитика»; its callbacks go to ua_visitors_bot.
- analitika_bot.py: register() also registers ua_visitors_bot (the client bot already calls it).
Each file is pinned to its live hash; each fragment must occur exactly once and an applied one is refused.
"""
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
TAG = 'UA-VISITORS-UA-001'
NEW_MODULES = ('ua_visitors_ua.py', 'ua_visitors_bot.py')
SOURCE_SHA256 = {
    'analitika_yadro.py': 'c9428882b8c04f275b02502a52d6683a446fc494c8d6ff59e0438f1d9e6ace60',
    'analitika_knopka.py': '729a38eb4f694623eca4c7a92e1521de5044a5dcba0b2960cb79d8c2d87f6dba',
    'analitika_bot.py': '77a46557811ce20b45a2025c2ae8913c3cb0f4e4f7729bcfaa53a6699a79ff1c',
}
# The client bot's screens route every v_an_ callback to analitika_knopka; served unchanged.
DEPENDENCY_SHA256 = {'vitrina.py': 'cf672c972405315195b1099ac6cac43d42eb7a786e3fc9aec5fa086a3f5a88b9'}
EDITS = {
    'analitika_yadro.py': (
        ('    c.execute("CREATE TABLE IF NOT EXISTS sutki(den TEXT PRIMARY KEY, svodka TEXT)")\n',
         '    c.execute("CREATE TABLE IF NOT EXISTS sutki(den TEXT PRIMARY KEY, svodka TEXT)")\n'
         '    for _kol in ("tz", "lg", "dv"):  # ' + TAG + ': browser time zone, language, device type\n'
         '        try:\n'
         '            c.execute("ALTER TABLE sessions ADD COLUMN %s TEXT" % _kol)\n'
         '        except sqlite3.OperationalError:\n'
         '            pass\n'),
        ('    uk   = str(dannye.get("uk", ""))[:120]\n',
         '    uk   = str(dannye.get("uk", ""))[:120]\n'
         '    tz   = str(dannye.get("tz", ""))[:40]  # ' + TAG + '\n'
         '    lg   = str(dannye.get("lg", ""))[:20]\n'
         '    dv   = str(dannye.get("dv", ""))[:1]\n'),
        ('    c.execute("INSERT OR IGNORE INTO sessions(sid,vid,nachalo,konec,istochnik,utm_source,utm_medium,utm_campaign,'
         'utm_content,put) VALUES(?,?,?,?,?,?,?,?,?,?)",\n              (sid, vid, ts, ts, ist, us, um, uc, uk, ""))\n',
         '    c.execute("INSERT OR IGNORE INTO sessions(sid,vid,nachalo,konec,istochnik,utm_source,utm_medium,utm_campaign,'
         'utm_content,put,tz,lg,dv) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",\n'
         '              (sid, vid, ts, ts, ist, us, um, uc, uk, "", tz, lg, dv))  # ' + TAG + '\n'),
        ("function set(k,v,st){ try{ st.setItem(k,v); }catch(e){} }\n",
         "function set(k,v,st){ try{ st.setItem(k,v); }catch(e){} }\n"
         "var stf=new URLSearchParams(location.search).get('ua_staff'); // " + TAG + ": staff devices are not counted\n"
         "if(stf==='1'){ set('ua_staff','1',LS); } if(stf==='0'){ try{ LS.removeItem('ua_staff'); }catch(e){} }\n"
         "if(get('ua_staff',LS)==='1'){ return; }\n"
         "var TZ=''; try{ TZ=Intl.DateTimeFormat().resolvedOptions().timeZone||''; }catch(e){}\n"
         "var LG=(navigator.language||'').slice(0,20);\n"
         "var UA=navigator.userAgent||''; var DV=/iPad|Tablet/i.test(UA)?'t':(/Mobi|Android|iPhone/i.test(UA)?'m':'d');\n"),
        ("function istochnik(){\n  if(us){",
         "function istochnik(){\n  if(par.get('gclid')||par.get('gbraid')||par.get('wbraid')){ return 'Реклама Google'; }\n  if(us){"),
        ("         i:ist,us:us,um:um,uc:uc,uk:uk};\n",
         "         i:ist,us:us,um:um,uc:uc,uk:uk,tz:TZ,lg:LG,dv:DV};\n"),
    ),
    'analitika_knopka.py': (
        ('        [("🔄 Обновить", "v_an_today")],\n',
         '        [("🔄 Обновить", "v_an_today")],\n'
         '        [("🇺🇦 Посетители из Украины", "v_an_ua")],  # ' + TAG + '\n'),
        ('    if not vladelec_li(kto):\n        return True\n',
         '    if not vladelec_li(kto):\n        return True\n'
         '    if deystvie.startswith("v_an_ua"):  # ' + TAG + '\n'
         '        import ua_visitors_bot\n'
         '        return await ua_visitors_bot.vetka(bot, chat_id, kto, deystvie)\n'),
    ),
    'analitika_bot.py': (
        ('    app.add_handler(CallbackQueryHandler(_cb, pattern=r"^ana_"), group=-1)\n    return True',
         '    app.add_handler(CallbackQueryHandler(_cb, pattern=r"^ana_"), group=-1)\n'
         '    try:  # ' + TAG + ': «Посетители из Украины» (custom period, 09:00 summary)\n'
         '        import ua_visitors_bot\n'
         '        ua_visitors_bot.register(app)\n'
         '    except Exception as _e_vua:\n'
         '        print("ua_visitors_bot:", _e_vua)\n'
         '    return True'),
    ),
}


def targets(root):
    return tuple(SOURCE_SHA256)


def is_page(name):
    return False


def page_names(root):
    return ()


def edit(name, text):
    if TAG in text:
        raise ValueError('VISITORS_ALREADY_APPLIED:' + name)
    for old, new in EDITS[name]:
        if text.count(old) != 1:
            raise ValueError('VISITORS_FRAGMENT:' + name + ':' + old[:40])
        text = text.replace(old, new)
    return text


def build(source, dependencies):
    for name, digest in {**SOURCE_SHA256, **DEPENDENCY_SHA256}.items():
        value = source.get(name, dependencies.get(name))
        if value is None or hashlib.sha256(value).hexdigest() != digest:
            raise ValueError('INPUT_HASH:' + name)
    result = {name: (HERE / name).read_bytes() for name in NEW_MODULES}
    result.update({name: edit(name, source[name].decode('utf-8')).encode('utf-8') for name in EDITS})
    return result
