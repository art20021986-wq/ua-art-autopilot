"""VIDEO-LIMIT-001 stage A on the server: build the official Telegram Bot API server (owner 2026-11-19 «1 да»).

Resumable: every step is skipped when its result is already there, and the compile runs at most BUILD_SECONDS per run
(make keeps finished objects, so the next run continues). Everything is written only inside WORK, a folder of the private
inbox; the CRM bot, the site, the CRM database and Telegram are not touched. One compile thread at the lowest priority.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shutil
import signal
import subprocess
import time
import urllib.request

HERE = Path(__file__).resolve().parent
WORK = HERE.parent / 'videobuild_work'
GPERF_URL = 'https://ftp.gnu.org/gnu/gperf/gperf-3.1.tar.gz'
GPERF_SHA256 = '588546b945bba4b70b6a3a616e80b4ab466e3f33024a352fc2198112cdbb3ae2'
REPO = 'https://github.com/tdlib/telegram-bot-api.git'
COMMIT = '7232881b39dfcd048a0d569f1983c5184249ee05'
BUILD_SECONDS = 40 * 60
LONG_NUMBER = re.compile(r'\d{9,}')


def run(args, cwd=None, timeout=900, log=None):
    """Run one step at the lowest priority in its own process group; on timeout stop the whole group (make and
    compilers too) — finished objects stay for the next run. Return (code, seconds, last lines of the output)."""
    started = time.monotonic()
    process = subprocess.Popen(['nice', '-n', '19'] + [str(a) for a in args], cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        output, _ = process.communicate(timeout=timeout)
        code = process.returncode
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            output, _ = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
        code = 'TIMEOUT'
    output = output or ''
    if log is not None:
        with open(log, 'a', encoding='utf-8') as handle:
            handle.write(output)
    tail = [LONG_NUMBER.sub('[N]', line)[:200] for line in output.splitlines()[-15:]]
    return code, round(time.monotonic() - started), tail


def gperf(steps):
    binary = WORK / 'gperf/bin/gperf'
    if shutil.which('gperf') or binary.is_file():
        steps.append({'step': 'gperf', 'status': 'present'})
        return shutil.which('gperf') or str(binary)
    archive = WORK / 'gperf-3.1.tar.gz'
    if not archive.is_file():
        with urllib.request.urlopen(GPERF_URL, timeout=120) as response:
            data = response.read(10 * 2**20)
        if hashlib.sha256(data).hexdigest() != GPERF_SHA256:
            raise RuntimeError('GPERF_SHA256')
        archive.write_bytes(data)
    source = WORK / 'gperf-3.1'
    if not source.is_dir():
        run(['tar', 'xzf', archive], cwd=WORK)
    for name, args in (('configure', ['./configure', '--prefix=' + str(WORK / 'gperf')]),
                       ('make', ['make', '-j1']), ('install', ['make', 'install'])):
        code, seconds, tail = run(args, cwd=source)
        steps.append({'step': 'gperf_' + name, 'code': code, 'seconds': seconds, 'tail': tail if code else []})
        if code != 0:
            raise RuntimeError('GPERF_' + name.upper())
    return str(binary)


def sources(steps):
    source = WORK / 'telegram-bot-api'
    if not (source / '.git').is_dir():
        code, seconds, tail = run(['git', 'clone', '--quiet', REPO, source], cwd=WORK, timeout=900)
        steps.append({'step': 'clone', 'code': code, 'seconds': seconds, 'tail': tail if code else []})
        if code != 0:
            raise RuntimeError('CLONE')
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=source, capture_output=True, text=True).stdout.strip()
    if head != COMMIT:
        for name, args in (('fetch', ['git', 'fetch', '--quiet', 'origin', COMMIT]),
                           ('checkout', ['git', 'checkout', '--quiet', COMMIT])):
            code, seconds, tail = run(args, cwd=source, timeout=600)
            steps.append({'step': name, 'code': code, 'seconds': seconds, 'tail': tail if code else []})
            if code != 0:
                raise RuntimeError(name.upper())
    if not (source / 'td' / 'CMakeLists.txt').is_file():
        code, seconds, tail = run(['git', 'submodule', 'update', '--init', '--recursive', '--quiet'], cwd=source,
                                  timeout=1200)
        steps.append({'step': 'submodules', 'code': code, 'seconds': seconds, 'tail': tail if code else []})
        if code != 0:
            raise RuntimeError('SUBMODULES')
    steps.append({'step': 'sources', 'commit': COMMIT})
    return source


def build(steps, source, gperf_binary, budget):
    build_dir = WORK / 'build'
    install = WORK / 'install'
    binary = install / 'bin' / 'telegram-bot-api'
    if binary.is_file():
        steps.append({'step': 'build', 'status': 'present'})
        return binary
    if not (build_dir / 'CMakeCache.txt').is_file():
        build_dir.mkdir(exist_ok=True)
        code, seconds, tail = run(['cmake', '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_INSTALL_PREFIX=' + str(install),
                                   '-DGPERF_EXECUTABLE=' + gperf_binary, '-S', source, '-B', build_dir], timeout=900)
        steps.append({'step': 'cmake', 'code': code, 'seconds': seconds, 'tail': tail if code else []})
        if code != 0:
            raise RuntimeError('CMAKE')
    code, seconds, tail = run(['cmake', '--build', build_dir, '--target', 'install', '-j', '1'],
                              timeout=max(60, budget), log=WORK / 'build.log')
    percent = [m for line in tail for m in re.findall(r'\[\s*(\d+)%\]', line)]
    steps.append({'step': 'compile', 'code': code, 'seconds': seconds, 'progress_percent': percent[-1] if percent else None,
                  'tail': tail[-8:]})
    return binary if binary.is_file() else None


def report():
    started = time.monotonic()
    WORK.mkdir(mode=0o700, exist_ok=True)
    steps = []
    value = {'status': 'PASS', 'work': str(WORK), 'steps': steps}
    try:
        gperf_binary = gperf(steps)
        source = sources(steps)
        binary = build(steps, source, gperf_binary, BUILD_SECONDS - int(time.monotonic() - started))
        value['built'] = bool(binary)
        if binary:
            value['version'] = run([binary, '--version'], timeout=30)[2][-1:]
            value['binary_bytes'] = binary.stat().st_size
    except Exception as error:
        value.update(status='FAIL', error=type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160])
    usage = subprocess.run(['du', '-s', '-B1', str(WORK)], capture_output=True, text=True, timeout=300).stdout.split('\t')[0]
    value.update(work_bytes=usage, seconds=round(time.monotonic() - started))
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (3000, 3010))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0,
                 writes_scope='private inbox folder videobuild_work only')
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
