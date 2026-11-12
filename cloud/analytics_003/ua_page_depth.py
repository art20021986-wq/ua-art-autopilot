"""Block «📜 СТРАНИЦЫ: ДОЧИТАЛИ И НАЖИМАЛИ» of the client bot «Аналитика» report (owner «Да» 2026-11-12).

For the most viewed pages of the period: the share of page views read to the middle and to the end (the page script
sends one 'scroll' event at 50% and one at 95% of the page per view) and the most frequent clicks on that page.
Works only on the events the report already read; the block is left out until read-depth events exist.
"""
TOP_PAGES = 5
TOP_CLICKS = 3


def _procent(chast, vse):
    return min(100, int(round(100.0 * chast / vse))) if vse else 0


def _prosmotrov(n):
    if n % 10 == 1 and n % 100 != 11:
        return 'просмотр'
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return 'просмотра'
    return 'просмотров'


def stroki(sobytiya, nazvanie, deystvie, sistemnye):
    """sobytiya: report events (tip, adres, z); nazvanie(adres): page name; deystvie(s): click name or None for a
    page view; sistemnye: event types that are neither views nor clicks."""
    prosmotry, seredina, konec, nazhatiya = {}, {}, {}, {}
    for s in sobytiya:
        tip = (s.get('tip') or '').lower()
        stranica = nazvanie(s.get('adres'))
        if tip == 'scroll':
            schet = {'50': seredina, '100': konec}.get(str(s.get('z') or ''))
            if schet is not None:
                schet[stranica] = schet.get(stranica, 0) + 1
            continue
        if tip in sistemnye:
            continue
        # A car card or diagnostics page reports its own view as 'card' / 'diag' with no label (a click on a
        # diagnostics link carries the link text).
        imya = None if tip in ('card', 'diag') and not s.get('z') else deystvie(s)
        if imya is None:
            prosmotry[stranica] = prosmotry.get(stranica, 0) + 1
        else:
            po_stranice = nazhatiya.setdefault(stranica, {})
            po_stranice[imya] = po_stranice.get(imya, 0) + 1
    if not (seredina or konec):
        return []
    itog = ['', '📜 <b>СТРАНИЦЫ: ДОЧИТАЛИ И НАЖИМАЛИ</b>']
    for stranica, n in sorted(prosmotry.items(), key=lambda x: (-x[1], x[0]))[:TOP_PAGES]:
        itog.append('%s — %d %s' % (stranica, n, _prosmotrov(n)))
        itog.append('  дочитали: до середины %d%% · до конца %d%%' % (
            _procent(seredina.get(stranica, 0), n), _procent(konec.get(stranica, 0), n)))
        klik = sorted(nazhatiya.get(stranica, {}).items(), key=lambda x: (-x[1], x[0]))[:TOP_CLICKS]
        if klik:
            itog.append('  нажимали: ' + ' · '.join('%s %d' % pair for pair in klik))
    return itog
