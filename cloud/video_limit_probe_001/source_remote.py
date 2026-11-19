"""Read-only probe on the server for VIDEO-LIMIT-001 (owner 2026-11-19: raise the CRM bot video length and size to the
maximum possible now).

Reads only:
- build tools for the official Telegram Bot API server (cmake, g++, make, gperf, openssl and zlib headers), memory,
  processor count and the user process limit;
- whether a process inside this task can listen on localhost and be reached there, and whether Telegram's servers
  answer from here (a TCP connect only, nothing is sent);
- published card videos (count, total and largest size, durations via ffprobe if present) and disk use of the video folder;
- the sanitized server lines that download, convert and limit card videos (getFile, ffmpeg, size limits).
Nothing is written outside this run's own receipt.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import socket
import subprocess
import threading

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
MAX_SOURCE = 900 * 1024
TOOLS = ('cmake', 'g++', 'gcc', 'make', 'gperf', 'git', 'ffmpeg', 'ffprobe')
HEADERS = ('/usr/include/openssl/ssl.h', '/usr/include/zlib.h')
TELEGRAM = (('149.154.167.50', 443), ('149.154.175.53', 443), ('api.telegram.org', 443))
VIDEO_NEEDLE = re.compile(r'getFile|get_file|ffmpeg|ffprobe|PREDEL_VIDEO|20 ?МБ|20 \* 1024|file_size|\.mp4|download_to|base_url|'
                          r'local_mode|base_file_url')
SKIP_DIRS = {'backups', 'autopilot_inbox', 'node_modules', 'video', 'site', '__pycache__'}
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


def run(args, timeout=20):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return (result.stdout or result.stderr).strip()[:300]
    except Exception as error:
        return 'ERR:' + type(error).__name__


def machine():
    meminfo = {}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            key, value = line.split(':', 1)
            if key in ('MemTotal', 'MemAvailable'):
                meminfo[key] = value.strip()
    except Exception:
        pass
    tools = {name: shutil.which(name) for name in TOOLS}
    versions = {name: run([tools[name], '--version'])[:120] for name in ('cmake', 'g++', 'ffmpeg') if tools[name]}
    return {'tools': tools, 'versions': versions, 'headers': {h: Path(h).is_file() for h in HEADERS},
            'cpu_count': os.cpu_count(), 'memory': meminfo,
            'process_limit': resource.getrlimit(resource.RLIMIT_NPROC),
            'address_space_limit': resource.getrlimit(resource.RLIMIT_AS),
            'os': run(['uname', '-srm']), 'python': run(['python3.10', '--version'])}


def localhost():
    """Listen on 127.0.0.1 inside this task and connect to it from a thread (as a local Bot API server would be used)."""
    result = {}
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.settimeout(5)
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        got = []

        def accept():
            try:
                connection, _ = server.accept()
                got.append(connection.recv(16))
                connection.close()
            except Exception as error:
                got.append(type(error).__name__.encode())

        worker = threading.Thread(target=accept)
        worker.start()
        with socket.create_connection(('127.0.0.1', port), timeout=5) as client:
            client.sendall(b'ping')
        worker.join(6)
        server.close()
        result = {'listen': True, 'roundtrip': got == [b'ping']}
    except Exception as error:
        result = {'listen': False, 'error': type(error).__name__ + ':' + str(error)[:120]}
    return result


def telegram():
    """TCP connect only (no data sent): can a server process here reach Telegram's data centres and Bot API host."""
    result = {}
    for host, port in TELEGRAM:
        try:
            with socket.create_connection((host, port), timeout=6):
                result['%s:%d' % (host, port)] = 'connected'
        except Exception as error:
            result['%s:%d' % (host, port)] = type(error).__name__
    return result


def videos():
    base = HOME / 'video'
    files = [p for p in base.rglob('*.mp4') if p.is_file() and not p.is_symlink()] if base.is_dir() else []
    sizes = sorted((p.stat().st_size for p in files), reverse=True)
    probe = shutil.which('ffprobe')
    durations = []
    for path in sorted(files, key=lambda p: p.stat().st_size, reverse=True)[:8]:
        if probe:
            value = run([probe, '-v', 'error', '-show_entries', 'format=duration:stream=width,height,bit_rate',
                         '-of', 'json', str(path)], timeout=20)
            durations.append({'bytes': path.stat().st_size, 'ffprobe': value[:300]})
        else:
            durations.append({'bytes': path.stat().st_size})
    usage = shutil.disk_usage(HOME)
    return {'count': len(files), 'total_bytes': sum(sizes), 'largest_bytes': sizes[:10],
            'over_10mb': sum(1 for s in sizes if s > 10 * 2**20), 'largest_details': durations,
            'video_folder_bytes': run(['du', '-s', '-B1', str(base)], timeout=120).split('\t')[0],
            'shared_filesystem_free_bytes': usage.free}


def text_of(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_SOURCE:
        return None
    return path.read_bytes().decode('utf-8', 'replace')


def sources():
    found = {}
    for path in sorted(list(HOME.glob('*.py')) + list(HOME.glob('*/*.py'))):
        relative = path.relative_to(HOME)
        if any(part.startswith('.') or part in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        text = text_of(path)
        if text is None or not VIDEO_NEEDLE.search(text):
            continue
        lines = text.splitlines()
        hits = sorted({i for n, line in enumerate(lines) if VIDEO_NEEDLE.search(line)
                       for i in range(max(0, n - 4), min(len(lines), n + 5))})
        found[str(relative)] = {'sha256': hashlib.sha256(text.encode()).hexdigest()[:16],
                                'lines': [{'line': n + 1, 'text': sanitized_line(lines[n])[:240]} for n in hits][:160]}
        if len(found) >= 40:
            break
    return found


def report():
    value = {'status': 'PASS'}
    for key, call in (('machine', machine), ('localhost', localhost), ('telegram', telegram),
                      ('videos', videos), ('sources', sources)):
        try:
            value[key] = call()
        except Exception as error:
            value[key] = {'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (240, 250))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
