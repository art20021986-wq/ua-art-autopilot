"""Exact edit of the installed cars_ui.py: the ORDER-PROCESS-001 menu block (installed 2026-11-05 by
CRM-MENU-INSTALL-20261105) now hands the role's full menu to ua_menu_extra as well. Nothing else changes."""
MARK = '# ORDER-PROCESS-001 menu'
OLD = '''        import ua_menu_extra
        return ua_menu_extra.with_buttons(menu)
'''
NEW = '''        import ua_menu_extra
        return ua_menu_extra.with_buttons(markup, menu)  # R2: owner-approved «Клиенты» and «Сотрудники»
'''


class CandidateError(RuntimeError):
    pass


def cars_ui(source):
    if source.count(MARK) != 1 or source.count(OLD) != 1 or NEW in source:
        raise CandidateError('CARS_UI_FRAGMENT')
    return source.replace(OLD, NEW, 1)
