"""Exact edit of the installed access guard bezopasnost.py (ORDER-PROCESS-001, owner «Да» 2026-11-05): before refusing
an unknown person, a valid one-time staff invite from the CRM bot passes on to the bot. Nothing else changes; strangers
without a code are still refused and reported to the owner."""
MARK = '# ORDER-PROCESS-001 staff invite'
OLD = '''        _log("dostup vydan: " + str(kto))
        return True

    d = _sost()
'''
NEW = '''        _log("dostup vydan: " + str(kto))
        return True

    ''' + MARK + ''': a CRM invite from «Сотрудники» goes on to the bot, which gives the role.
    try:
        import ua_staff_invite
        if ua_staff_invite.valid(tekst, DB):
            _dobavit_v_dostup(kto, "по коду CRM")
            _log("dostup po kodu CRM: " + str(kto))
            return True
    except Exception as e:
        _log("kod CRM: " + repr(e))

    d = _sost()
'''


class CandidateError(RuntimeError):
    pass


def guard(source):
    if MARK in source or source.count(OLD) != 1:
        raise CandidateError('GUARD_FRAGMENT')
    return source.replace(OLD, NEW, 1)
