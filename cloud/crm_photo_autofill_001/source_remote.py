"""Read-only probe on the server: why an AUTO.RIA screenshot gave «Поля CRM не распознаны» (CRM-PHOTO-PROBE).

Reads only. Returns, sanitized: the photo path sources (team_bot.py, local_ocr.py, ai_fast_schema.py,
ai_filter.py, db.py) with sha256; the installed Tesseract version and languages; the live local_ocr
result and per-pass timings for the bundled sample screenshot; the CRM bot log lines of today that
mention the photo path; the cars table column names and whether the sample VIN is already in the CRM
(a count only). Nothing is written outside this run's own receipt.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import sqlite3
import subprocess
import sys
import time

import sample_image

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
FULL = ('team_bot.py', 'local_ocr.py', 'ai_fast_schema.py', 'ai_filter.py', 'db.py')
SAMPLE_VIN = 'WDD2452322J660244'
LOG = Path('/var/log/alwayson-log-266084.log')
LOG_TAIL = 4 * 1024 * 1024
LOG_TOPIC = re.compile(r'(?i)ocr|inbox|photo|фото|vin|traceback|error|exception|ai_')
MAX_SOURCE = 900 * 1024
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|schema\.org)(?:[/\'"\s]|$)')


def sanitized_line(line):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    return LONG_NUMBER.sub('[N]', line)


def sources():
    files = {}
    for name in FULL:
        path = HOME / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_SOURCE:
            files[name] = None
            continue
        raw = path.read_bytes()
        files[name] = {'sha256': hashlib.sha256(raw).hexdigest(),
                       'source': '\n'.join(sanitized_line(x) for x in raw.decode('utf-8', 'replace').splitlines())}
    return files


def tesseract():
    binary = shutil.which('tesseract')
    if not binary:
        return {'binary': None}
    version = subprocess.run([binary, '--version'], capture_output=True, text=True, timeout=10, check=False)
    langs = subprocess.run([binary, '--list-langs'], capture_output=True, text=True, timeout=10, check=False)
    return {'binary': binary, 'version': (version.stdout or version.stderr).splitlines()[:3],
            'languages': langs.stdout.split()[4:] if 'List of' in langs.stdout else langs.stdout.split(),
            'cpu_count': os.cpu_count(), 'load_average': os.getloadavg()}


def ocr(image, home=None):
    """Run the installed local_ocr exactly as the bot does, then time each pass without the 1.45 s cap."""
    sys.path.insert(0, str(home or HOME))
    import local_ocr
    started = time.monotonic()
    text = local_ocr.image_text(image, hard_seconds=14.0)
    live = {'seconds': round(time.monotonic() - started, 2), 'text_chars': len(text),
            'vin_in_text': SAMPLE_VIN in text.upper(),
            'fields': local_ocr.fields_from_text(text, {'vin', 'brand', 'model', 'year', 'mileage_km', 'fuel',
                                                        'gearbox', 'drive', 'engine_cc'})}
    binary = shutil.which('tesseract')
    if not binary:
        return {'live': live, 'passes': []}
    from PIL import Image
    import io
    original = Image.open(io.BytesIO(image)).convert('RGB')
    width, height = original.size
    languages = local_ocr._languages(binary)
    tile_w, tile_h = max(32, int(width * 0.56)), max(32, int(height * 0.34))
    jobs = [('full', original.copy(), 2 if max(width, height) < 2200 else 1, 11)]
    for y in (0, max(0, int((height - tile_h) * 0.34)), max(0, int((height - tile_h) * 0.67)), max(0, height - tile_h)):
        for x in (max(0, width - tile_w), 0):
            tile = original.crop((x, y, min(width, x + tile_w), min(height, y + tile_h)))
            jobs.append(('tile_%d_%d' % (x, y), tile, 3 if max(tile.size) < 1800 else 2, 3))
    passes = []
    for name, picture, scale, psm in jobs:
        prepared = local_ocr._prepare(picture, scale)
        target = HERE / 'runs' / ('pass_%s.png' % name)
        prepared.save(target, format='PNG')
        try:
            begun = time.monotonic()
            result = subprocess.run([binary, str(target), 'stdout', '-l', languages, '--psm', str(psm)],
                                    capture_output=True, text=True, timeout=60, check=False)
            out = result.stdout if result.returncode == 0 else ''
            passes.append({'pass': name, 'pixels': list(prepared.size), 'seconds': round(time.monotonic() - begun, 2),
                           'over_live_cap_1_45': time.monotonic() - begun > 1.45, 'chars': len(out),
                           'vin_found': SAMPLE_VIN in out.upper()})
        except subprocess.TimeoutExpired:
            passes.append({'pass': name, 'seconds': 60, 'timeout': True})
        finally:
            target.unlink(missing_ok=True)
    return {'languages_used': languages, 'live': live, 'passes': passes}


def bot_log(today):
    if not LOG.is_file():
        return None
    with LOG.open('rb') as handle:
        handle.seek(max(0, LOG.stat().st_size - LOG_TAIL))
        lines = handle.read().decode('utf-8', 'replace').splitlines()
    marks = (today.strftime('%b %d'), today.strftime('%b ') + str(today.day).rjust(2), today.isoformat())
    picked = [sanitized_line(x)[:300] for x in lines if any(m in x for m in marks) and LOG_TOPIC.search(x)]
    return {'today_lines': len(picked), 'lines': picked[-300:]}


def crm(database=None):
    path = database or HOME / 'crm.db'
    con = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        columns = [row[1] for row in con.execute('PRAGMA table_info(cars)')]
        count = con.execute("SELECT COUNT(*) FROM cars WHERE UPPER(REPLACE(REPLACE(COALESCE(vin, ''), ' ', ''), '-', '')) = ?",
                            (SAMPLE_VIN,)).fetchone()[0]
        return {'cars_columns': columns, 'sample_vin_cards': count}
    finally:
        con.close()


def report():
    value = {'status': 'PASS', 'files': sources(), 'tesseract': tesseract()}
    for key, call in (('ocr', lambda: ocr(sample_image.JPEG)),
                      ('bot_log', lambda: bot_log(datetime.date.today())),
                      ('crm', crm)):
        try:
            value[key] = call()
        except Exception as error:
            value[key] = {'error': type(error).__name__ + ':' + str(error)[:160]}
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (120, 130))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + str(error)[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
