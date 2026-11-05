"""Read-only: download public photos and video of one catalog car for ad editing.

Usage: python3 -I fetch.py UA-0018 OUT_DIR
Only public pages of www.uaart.com.ua are read; nothing is written to the site.
"""
import re
import sys
import urllib.request
from pathlib import Path

BASE = 'https://www.uaart.com.ua/video/'
UA = 'Mozilla/5.0 (compatible; UA-ART-autopilot/1.0)'


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def media_paths(html, code):
    photos = sorted(set(re.findall(r'foto/%s/\d+\.jpg' % re.escape(code), html)))
    videos = sorted(set(re.findall(r'[\w./-]*%s[\w-]*\.mp4' % re.escape(code), html)))
    return photos, videos


def main(code, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    html = get(BASE + code + '.html').decode('utf-8', 'replace')
    (out / 'page.html').write_text(html, encoding='utf-8')
    photos, videos = media_paths(html, code)
    for rel in photos + videos:
        data = get(BASE + rel)
        (out / Path(rel).name).write_bytes(data)
        print(rel, len(data))
    print('photos', len(photos), 'videos', len(videos))
    return 0 if photos else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
