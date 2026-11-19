"""Read-only probe BIG-VIDEO on the server (owner 2026-11-19: Telethon only for downloading videos over 20 MB).

Inside WORK (a temporary folder of the private inbox) only: install Telethon there, log in as the CRM bot over MTProto
with an in-memory session and updates off (no logOut: the bot keeps working on the Bot API), find the newest video over
20 MB sent by an owner (by message number, messages.getMessages), download it to WORK, measure size, duration, speed
and CPU, then remove WORK. The key file and the bot token are read only to log in; their values never leave this process.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import resource
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
HOME = Path('/home/Carix')
WORK = HERE.parent / 'bigvideo_probe_work'
PACKAGES = ('telethon==1.46.0', 'pyaes', 'rsa', 'cryptg==0.4.0')  # R2: newer cryptg lacks decrypt_ige
BIG = 20 * 1024 * 1024
SCAN = 1000
LONG_NUMBER = re.compile(r'\d{6,}')


SECRET_LIKE = re.compile(r'\d+:[A-Za-z0-9_-]{6,}|[0-9a-fA-F]{32}|[A-Z0-9_]{12,}')


def clean(text):
    """Error text for the report: anything shaped like a bot token, the api_hash or a long secret is removed."""
    return LONG_NUMBER.sub('[N]', SECRET_LIKE.sub('[SECRET]', str(text)))[:200]


def secrets():
    lines = [x.strip() for x in (HOME / 'telegram_api.txt').read_text(encoding='utf-8').splitlines() if x.strip()]
    token = (HOME / 'team_token.txt').read_text(encoding='utf-8').strip()
    if len(lines) != 2 or not lines[0].isdigit() or not re.fullmatch(r'[0-9a-f]{32}', lines[1]) or ':' not in token:
        raise RuntimeError('KEY_OR_TOKEN_FORMAT')
    return int(lines[0]), lines[1], token


def owners():
    sys.path.insert(0, str(HOME))
    import db
    return {int(x) for x in db.staff_ids_by_role(db.ROLE_OWNER)}


def install():
    started = time.monotonic()
    result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', '--disable-pip-version-check',
                             '--target', str(WORK / 'lib')] + list(PACKAGES),
                            capture_output=True, text=True, timeout=600, check=False)
    if result.returncode != 0:
        raise RuntimeError('PIP:' + clean(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else ''))
    sys.path.insert(0, str(WORK / 'lib'))
    return round(time.monotonic() - started)


def video_size(message):
    document = getattr(getattr(message, 'media', None), 'document', None)
    if document is None or not str(getattr(document, 'mime_type', '')).startswith('video/'):
        return 0
    return int(document.size or 0)


async def probe(value):
    from telethon import TelegramClient, functions, types
    from telethon.sessions import StringSession
    api_id, api_hash, token = secrets()
    owner_ids = owners()
    client = TelegramClient(StringSession(), api_id, api_hash, receive_updates=False)
    await client.start(bot_token=token)
    try:
        async def existing(ids):
            result = await client(functions.messages.GetMessagesRequest(id=[types.InputMessageID(i) for i in ids]))
            return [m for m in result.messages if not isinstance(m, types.MessageEmpty)]

        async def any_from(start):  # message numbers have gaps (deleted messages): look at a window of 100
            return await existing(list(range(start, start + 100)))

        low, high = 1, 100
        while await any_from(high):
            low, high = high, high * 2
        while high - low > 100:  # newest window with messages among the bot's private chats
            middle = (low + high) // 2
            low, high = (middle, high) if await any_from(middle) else (low, middle)
        while await any_from(low + 100):
            low += 100
        window = await any_from(low)
        low = max([m.id for m in window] or [low])
        newest, found, seen = low, None, []
        value['newest_message'] = newest
        for start in range(newest, max(0, newest - SCAN), -100):
            batch = await existing(list(range(max(1, start - 99), start + 1)))
            for message in sorted(batch, key=lambda m: m.id, reverse=True):
                sender = getattr(getattr(message, 'peer_id', None), 'user_id', None)
                media = getattr(message, 'media', None)
                document = getattr(media, 'document', None)
                seen.append({'back': newest - message.id, 'out': bool(message.out), 'owner': sender in owner_ids,
                             'media': type(media).__name__ if media else None,
                             'mime': str(getattr(document, 'mime_type', ''))[:20] if document else None,
                             'mb': round(int(getattr(document, 'size', 0) or 0) / 2**20, 1) if document else None})
                if not message.out and sender in owner_ids and video_size(message) > BIG:
                    found = message
                    break
            if found:
                break
        value['scanned_from_newest'] = SCAN
        value['media_seen'] = [s for s in seen if s['media']][:60]
        value['messages_seen'] = len(seen)
        if not found:
            value['found'] = False
            return
        value.update(found=True, video_bytes=video_size(found), age_seconds=round(time.time() - found.date.timestamp()))
        target = WORK / 'video.mp4'
        cpu_before, started = resource.getrusage(resource.RUSAGE_SELF), time.monotonic()
        await client.download_media(found, file=str(target))
        seconds = time.monotonic() - started
        cpu_after = resource.getrusage(resource.RUSAGE_SELF)
        value.update(downloaded_bytes=target.stat().st_size, download_seconds=round(seconds, 1),
                     speed_mb_s=round(target.stat().st_size / 2**20 / max(seconds, 0.01), 2),
                     download_cpu_seconds=round(cpu_after.ru_utime + cpu_after.ru_stime
                                                - cpu_before.ru_utime - cpu_before.ru_stime, 1))
        ffprobe = shutil.which('ffprobe')
        if ffprobe:
            out = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration:stream=width,height',
                                  '-of', 'json', str(target)], capture_output=True, text=True, timeout=60).stdout
            data = json.loads(out or '{}')
            value['duration_seconds'] = round(float(data.get('format', {}).get('duration') or 0), 1)
            value['frame'] = [[s.get('width'), s.get('height')] for s in data.get('streams', []) if s.get('width')][:1]
    finally:
        await client.disconnect()


def report():
    WORK.mkdir(mode=0o700, exist_ok=True)
    value = {'status': 'PASS'}
    try:
        value['install_seconds'] = install()
        import cryptg  # noqa: F401  (fast decryption present)
        value['cryptg'] = True
        asyncio.run(probe(value))
    except Exception as error:
        value.update(status='FAIL', error=type(error).__name__ + ':' + clean(error))
    finally:
        problems = []
        shutil.rmtree(WORK, onerror=lambda function, path, info: problems.append(
            type(info[1]).__name__ + ':' + os.path.relpath(path, WORK)[:80]))
        value['work_removed'] = not WORK.exists()
        if problems:
            value['remove_problems'] = problems[:5]
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9]+', args.run):
        raise SystemExit('RUN_ID')
    resource.setrlimit(resource.RLIMIT_CPU, (1200, 1210))
    work = HERE / 'runs' / args.run
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    receipt = work / 'receipt-probe.json'
    if receipt.exists():
        return 0
    try:
        value = report()
    except Exception as error:
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + clean(error)}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0,
                 writes_scope='temporary inbox folder bigvideo_probe_work, removed at the end')
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
