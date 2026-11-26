"""Read-only probe for ADS-LP-001 (owner «Да» 2026-11-25: short enquiry form and «пригон» on the Kyiv «під ключ» pages).

Reads the live sources that build those pages and take the short form, so the change can be written against the real
files: ua_seo_landings.py, ua_seo_quick_form.py, ua_order/quick.py, ua_order/contract.py, video/order/quick-lead.js.
Every line is sanitized (secrets, foreign links and long numbers removed); sha256 of each file is reported.
Nothing is written outside this run's own receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
FILES = ('analitika_yadro.py', 'analitika_otchet.py', 'analitika_bot.py', 'ua_own_counter.py', 'ua_page_depth.py',
         'lead_bot.py')
# R3 (owner «да» 2026-11-26: «Посетители из Украины» in the client bot «📊 Аналитика»): the counter core, its reports,
# the bot screens, the page script injector and the client bot start file — to write the change against the live files.
SECRET = re.compile(r'(?i)(token|password|passwd|secret|api_key|api_hash|authorization|private_key)\w*\s*[\'"]?\s*[:=]'
                    r'|\b\d{6,12}:[A-Za-z0-9_-]{25,}\b|-----BEGIN')
LONG_NUMBER = re.compile(r'(?<!\d)\+?\d[\d\s()-]{8,}\d(?!\d)')
URL = re.compile(r'https?://[^\s\'"<>)]+')
PUBLIC_HOSTS = re.compile(r'https?://(?:www\.)?(?:uaart\.com\.ua|api\.telegram\.org)(?:[/\'"\s]|$)')


def sanitized_line(line):
    if SECRET.search(line):
        return '[REDACTED]'
    line = URL.sub(lambda m: m.group(0) if PUBLIC_HOSTS.match(m.group(0) + ' ') else '[URL]', line)
    return LONG_NUMBER.sub('[N]', line)


def read(relative, home=HOME):
    path = home / relative
    if not path.is_file():
        return {'present': False}
    data = path.read_bytes()
    text = data.decode('utf-8', 'replace')
    return {'present': True, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'source': '\n'.join(sanitized_line(line) for line in text.splitlines())}


def report(home=HOME):
    return {'status': 'PASS', 'files': {name: read(name, home) for name in FILES}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (60, 70))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
