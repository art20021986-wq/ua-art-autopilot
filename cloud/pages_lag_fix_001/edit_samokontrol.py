"""samokontrol.py (CRM self-check), PAGES-LAG-FIX-001.

When the pages were behind the database, one failed stranica.py run made the owner's alert, and the log kept only the
exit code. Now a failed run writes the end of its error output to samokontrol_log.txt and the rebuild is tried once more
a minute later; the owner is told only if both runs fail. Nothing else changes.
"""
from edits import replace_once

NAME = 'samokontrol.py'
MARK = 'PAGES-LAG-FIX-001'
OLD = '''    try:
        itog = subprocess.run([sys.executable, SBORSHCHIK], cwd=BAZA,
                              capture_output=True, text=True,
                              timeout=600)
        log("сборка запущена сторожем, код " + str(itog.returncode))
        return itog.returncode == 0
    except Exception as e:
        log("сборка не прошла: " + repr(e))
        return False
'''
NEW = '''    for popytka in (1, 2):  # PAGES-LAG-FIX-001: one more try before the owner is told
        try:
            itog = subprocess.run([sys.executable, SBORSHCHIK], cwd=BAZA,
                                  capture_output=True, text=True,
                                  timeout=600)
            log("сборка запущена сторожем, код " + str(itog.returncode))
            if itog.returncode == 0:
                return True
            hvost = ((itog.stderr or "") + "\\n" + (itog.stdout or "")).strip()
            log("ошибка сборки, попытка %d: %s" % (popytka, hvost[-600:].replace("\\n", " | ")))
        except Exception as e:
            log("сборка не прошла, попытка %d: %r" % (popytka, e))
        if popytka == 1:
            time.sleep(60)
    return False
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('SAMOKONTROL_ALREADY_INSTALLED')
    return replace_once(text, ((OLD, NEW),), NAME).encode('utf-8')
