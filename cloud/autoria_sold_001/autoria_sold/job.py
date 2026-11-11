"""Weekly server job: the owner's AUTO.RIA figures for the home reviews block (AUTORIA-SOLD-001).

Runs daily on PythonAnywhere and works on Mondays (Kyiv time), or on any day while the file is missing or lacks a
figure. Reads one public page of auto.ria.com (robots.txt respected) and writes video/brand/autoria-sold.json,
{"years": "5+", "sold": N, "reviews": N, "checked": "YYYY-MM-DD"}. A figure that cannot be read keeps its last
value; when none can be read nothing is written.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request
import urllib.robotparser
from zoneinfo import ZoneInfo

from . import page

ROOT = Path('/home/Carix')
OUT = ROOT / 'video/brand/autoria-sold.json'
DEALER_URL = 'https://auto.ria.com/uk/dealers/yua-art-kompani/3356/'
ROBOTS = 'https://auto.ria.com/robots.txt'
AGENT = 'UA-ART-autopilot/1.0 (+https://www.uaart.com.ua/)'
KYIV = ZoneInfo('Europe/Kyiv')
MONDAY = 0
FIELDS = ('years', 'sold', 'reviews')
MAX_BYTES = 6 * 1024 * 1024


def due(now, last):
    return now.weekday() == MONDAY or not all(name in last for name in FIELDS)


def current(path):
    """The figures written last time; an unreadable file counts as none."""
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {name: value[name] for name in FIELDS if name in value} if isinstance(value, dict) else {}


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': AGENT, 'Accept-Language': 'uk'})
    with urllib.request.urlopen(request, timeout=40) as response:
        return response.read(MAX_BYTES).decode('utf-8', 'replace')


def allowed(url):
    robots = urllib.robotparser.RobotFileParser()
    robots.parse(fetch(ROBOTS).splitlines())
    return robots.can_fetch(AGENT, url)


def write(path, data):
    """Atomic replace, so the site never serves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(dir=path.parent, prefix='.as-')
    try:
        with os.fdopen(handle, 'wb') as fh:
            fh.write(data)
        os.chmod(name, 0o644)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(now=None, out=OUT, get=fetch, robots=allowed):
    now = now or datetime.now(KYIV)
    last = current(out)
    if not due(now, last):
        return 0
    if not robots(DEALER_URL):
        print('AUTORIA_ROBOTS_DISALLOWED', file=sys.stderr)
        return 1
    found = page.figures(get(DEALER_URL))
    if not found:
        print('AUTORIA_FIGURES_NOT_FOUND', file=sys.stderr)
        return 1
    value = {**last, **found, 'checked': now.date().isoformat()}
    write(out, json.dumps(value, ensure_ascii=False).encode() + b'\n')
    print('AUTORIA_FIGURES', json.dumps(found))
    return 0
