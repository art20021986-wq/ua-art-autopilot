"""Weekly server job: the AUTO.RIA sold-cars number for the home reviews block (AUTORIA-SOLD-001).

Runs daily on PythonAnywhere and works on Mondays (Kyiv time), or on any day while the file is missing.
Reads one public page of auto.ria.com (robots.txt respected) and writes video/brand/autoria-sold.json,
{"sold": N, "checked": "YYYY-MM-DD"}. When the number cannot be read nothing is written.
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
MAX_BYTES = 6 * 1024 * 1024


def due(now, file_exists):
    return now.weekday() == MONDAY or not file_exists


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
    if not due(now, out.exists()):
        return 0
    if not robots(DEALER_URL):
        print('AUTORIA_ROBOTS_DISALLOWED', file=sys.stderr)
        return 1
    sold = page.sold_count(get(DEALER_URL))
    if sold is None:
        print('AUTORIA_SOLD_NOT_FOUND', file=sys.stderr)
        return 1
    write(out, json.dumps({'sold': sold, 'checked': now.date().isoformat()}).encode() + b'\n')
    print('AUTORIA_SOLD', sold)
    return 0
