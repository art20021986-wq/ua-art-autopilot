# ───────────────────────────── UA-MCF-DEDUP · ЗАЩИТА ОТ ДУБЛЕЙ ВИДЕО ─────────
# вызывается при КАЖДОЙ публикации карточки, до сборки HTML
try:
    import re as _dd_re, os as _dd_os
    import master_card as _DD

    _dd_ishodnaya = _zapisat_atomarno

    def _zapisat_atomarno(put, tekst):
        try:
            m = _dd_re.search(r"(UA-\d{4})", _dd_os.path.basename("%s" % put))
            if m and "-diag" not in "%s" % put:
                _DD.svesti_k_unikalnym(m.group(1))
        except Exception:
            pass
        return _dd_ishodnaya(put, tekst)
except Exception:
    pass
# ───────────────────────────── конец UA-MCF-DEDUP ────────────────────────────
