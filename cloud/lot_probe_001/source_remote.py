"""Read-only probe on the server for JPAUTO-KOREA-001 (owner 2026-11-11: auction day choice, VIN and all photos).

R2 (2026-11-11): the lot page markup differs from the collector's pattern, so every image address shape,
the table labels and the chassis/VIN lines (a 17-character VIN masked as [VIN17]) are reported too.
Uses the collector already installed on the server (/home/Carix/korea_auction) with the owner's login file, as the
hourly job does: reads the whole Korea search (lots per auction day), three lot pages (how many photos, whether the
specs have the chassis number — only its length is reported) and downloads three photos of one lot to measure their
size (kept in memory, never saved). Also reports the published lot list and photo folder sizes. Nothing is written
except this receipt; no bid is placed.
"""
import argparse
from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import re
import resource
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/Carix')
LONG_NUMBER = re.compile(r'\d{5,}')


def folder_size(path):
    files = [p for p in path.glob('*') if p.is_file()]
    return {'files': len(files), 'bytes': sum(p.stat().st_size for p in files)}


def published():
    """The lot list now on the site (read only)."""
    try:
        data = json.loads((ROOT / 'video/korea/lots.json').read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        return {'error': type(error).__name__}
    lots = data.get('lots', [])
    return {'auction_date': data.get('auction_date'), 'lots': len(lots),
            'priced': sum(1 for lot in lots if lot.get('start_krw')),
            'photos_per_lot': dict(Counter(len(lot.get('photos', [])) for lot in lots)),
            'keys': sorted(lots[0]) if lots else []}


def shape(url):
    """The photo address without host and numbers: shows whether it is a thumbnail or the full photo."""
    path = re.sub(r'^https?://[^/]+', '', url)
    return LONG_NUMBER.sub('[N]', path)[:120]


def report():
    sys.path.insert(0, str(ROOT))
    from korea_auction import collect, job, lots, selection, session
    browser = session.Session()
    browser.login(*job.read_login())
    total, all_lots = collect.fetch_all_lots(browser)
    days = Counter(selection.auction_date(lot) for lot in all_lots)
    by_day = [{'date': day, 'weekday': datetime.strptime(day, '%Y/%m/%d').strftime('%a'), 'lots': n,
               'starts': sorted({lot['auction_start'][11:] for lot in all_lots if selection.auction_date(lot) == day}),
               'houses': len({lot['house'] for lot in all_lots if selection.auction_date(lot) == day})}
              for day, n in sorted(days.items())]
    sample = [lot for lot in all_lots if lot.get('detail_url')][::max(1, len(all_lots) // 3)][:3]
    pages, measured = [], {}
    for lot in sample:
        _, html = browser.fetch(lot['detail_url'])
        detail = lots.parse_detail(html)
        chassis = detail['specs'].get('Chassis No.', '')
        all_imgs = re.findall(r'<img[^>]+src="([^"]+)"', html)
        labels = [re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', m)).strip()[:40]
                  for m in re.findall(r'<(?:th|dt)\b[^>]*>(.*?)</(?:th|dt)>', html, re.S | re.I)]
        vin_lines = [LONG_NUMBER.sub('[N]', re.sub(r'[A-HJ-NPR-Z0-9]{17}', '[VIN17]', re.sub(r'\s+', ' ', line)))[:200]
                     for line in html.splitlines() if re.search(r'(?i)chassis|\bvin\b|차대', line)][:15]
        img_attrs = sorted({shape(m) for m in re.findall(r'(?:data-src|data-original|data-lazy|href)="(https?://[^"]+\.(?:jpe?g|png|webp)[^"]*)"', html, re.I)})[:12]
        pages.append({'detail_photos': len(detail['photos']), 'results_photos': len(lot['photos']),
                      'chassis_length': len(chassis), 'chassis_looks_like_vin': bool(re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', chassis)),
                      'spec_labels': sorted(detail['specs'])[:40], 'img_tags': len(all_imgs),
                      'photo_shapes': sorted({shape(u) for u in detail['photos']})[:6],
                      'img_shapes': sorted({shape(u) for u in all_imgs})[:60], 'other_photo_links': img_attrs,
                      'labels': labels[:80], 'vin_lines': vin_lines,
                      'same_as_results': sum(1 for u in all_imgs if any(u.split('?')[0].endswith(r.rsplit('/', 1)[-1]) for r in lot['photos'])),
                      'results_photo_shapes': sorted({shape(u) for u in lot['photos']})[:3]})
        if not measured and detail['photos']:
            sizes = []
            for url in detail['photos'][:3]:
                try:
                    sizes.append(len(job.fetch_photo(url)))
                except (OSError, ValueError) as error:
                    sizes.append(type(error).__name__)
            measured = {'photo_bytes': sizes}
    return {'status': 'PASS', 'no_bid_placed': True, 'lots_total': total, 'lots_parsed': len(all_lots),
            'days': by_day, 'lot_pages': pages, **measured, 'requests': browser.requests,
            'published': published(), 'folders': {'lots': folder_size(ROOT / 'video/korea/lots'),
                                                  'img': folder_size(ROOT / 'video/korea/img')}}


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
        value = {'status': 'FAIL', 'error': type(error).__name__ + ':' + LONG_NUMBER.sub('[N]', str(error))[:160]}
    value.update(run_id=args.run, mode='probe', safe_to_stop=True, remote_write_count=0)
    temporary = work / '.receipt-probe.tmp'
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.chmod(temporary, 0o600)
    os.replace(temporary, receipt)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
