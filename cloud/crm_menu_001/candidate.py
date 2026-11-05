"""Exact edit of the installed cars_ui.py: one block at the end that wraps the current with_stats_button, as
the earlier blocks do (HOME-PHOTO-001). A failure inside only logs and keeps the previous menu."""
MARK = '# ORDER-PROCESS-001 menu'
BLOCK = '''

''' + MARK + ''': «Заявки с сайта» and «Ещё» in the main menu (module ua_menu_extra).
_ua_menu_extra_menu = with_stats_button


def with_stats_button(markup):
    menu = _ua_menu_extra_menu(markup)
    try:
        import ua_menu_extra
        return ua_menu_extra.with_buttons(menu)
    except Exception as e:
        log.warning('ua_menu_extra: кнопки не добавлены: %s', e)
        return menu
'''


class CandidateError(RuntimeError):
    pass


def cars_ui(source):
    if MARK in source or '\ndef with_stats_button(markup):' not in source:
        raise CandidateError('CARS_UI_FRAGMENT')
    return source.rstrip('\n') + '\n' + BLOCK
