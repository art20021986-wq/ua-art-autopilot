"""Python 3.10 usercustomize.py (runs at the start of every Python process of the account), PAGES-LAG-FIX-001.

Its «UA-V74 samokontrol» block started the CRM self-check in every process (bot, web app, server and autopilot tasks);
each copy could launch a full stranica.py rebuild on its own. Now the block imports samokontrol only in the bot process
(always-on task «python3.10 /home/Carix/start_safe.py», which runs run_all.py). Every other block is left as it is.
"""
from edits import replace_once

NAME = '.local/lib/python3.10/site-packages/usercustomize.py'
MARK = 'PAGES-LAG-FIX-001'
BOT_PROGRAMS = ('start_safe', 'run_all')
OLD = '''# UA-V74 samokontrol
try:
    import sys
    if '/home/Carix' not in sys.path:
        sys.path.insert(0, '/home/Carix')
    import samokontrol
except Exception:
    pass
'''
NEW = '''# UA-V74 samokontrol
try:
    import sys
    if '/home/Carix' not in sys.path:
        sys.path.insert(0, '/home/Carix')
    # PAGES-LAG-FIX-001: the CRM self-check runs only in the bot process (start_safe.py / run_all.py).
    if any(name in ' '.join(sys.argv) for name in ('start_safe', 'run_all')):
        import samokontrol
except Exception:
    pass
'''


def build(source):
    text = source.decode('utf-8')
    if MARK in text:
        raise ValueError('USERCUSTOMIZE_ALREADY_INSTALLED')
    return replace_once(text, ((OLD, NEW),), NAME).encode('utf-8')
