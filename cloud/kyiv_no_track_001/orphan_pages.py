"""Old card pages of cars no longer in the CRM (owner «2. Да», 2026-11-19): the CRM public sync never rewrites them,
so their delivery block loses the tracking here. Only pages at stage 4 (Kyiv) whose code has no CRM car are taken;
the edit removes the tracking widget (and its now empty metadata row) and nothing else.
"""
from contextlib import closing
import re
import sqlite3

import stage_preview

FOLDERS = ('video', 'video/ru', 'video/ua', 'site')
PAGE = re.compile(r'(UA-[0-9]{4,})(?:-[0-9a-f]{8})?\.html')


def crm_codes(root):
    with closing(sqlite3.connect((root / 'crm.db').as_uri() + '?mode=ro', uri=True, timeout=5)) as connection:
        return {str(row[0]) for row in connection.execute('SELECT auto_number FROM cars')}


def find(root, codes=None):
    codes = crm_codes(root) if codes is None else codes
    found = []
    for folder in FOLDERS:
        for path in sorted((root / folder).glob('UA-*.html')):
            match = PAGE.fullmatch(path.name)
            if not match or match.group(1) in codes or path.is_symlink():
                continue
            state = stage_preview.page_state(path.read_text(encoding='utf-8', errors='replace'))
            if state['stage'] == 4 and state['tracking'] != 'none':
                found.append(str(path.relative_to(root)))
    return tuple(found)


def build(source):
    text = source.decode('utf-8')
    if stage_preview.page_state(text)['stage'] != 4:
        raise ValueError('ORPHAN_NOT_KYIV')
    result = stage_preview.without_tracking(text)
    if result == text or stage_preview.tracking(result) != 'none':
        raise ValueError('ORPHAN_TRACKING_NOT_REMOVED')
    if len(text) - len(result) > 4000:
        raise ValueError('ORPHAN_EDIT_TOO_LARGE')
    return result.encode('utf-8')
