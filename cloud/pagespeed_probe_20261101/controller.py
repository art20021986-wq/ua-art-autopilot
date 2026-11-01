#!/usr/bin/env python3
"""Read-only speed probe for SEO item 9: Lighthouse (the PageSpeed Insights engine) on the runner.

The keyless PageSpeed Insights API quota is shared and exhausted minutes after its daily reset,
so the same lab test runs here: mobile preset (simulated slow 4G and CPU slowdown, as PageSpeed),
performance and SEO categories, three runs per page, the median run by performance score kept.
The site only receives the page loads a visitor's browser makes. No writes, no tokens.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

PACKAGE = 'cloud/pagespeed_probe_20261101'
TASKS = ('PAGESPEED-PROBE-20261101',)
ROOT = Path(__file__).resolve().parents[2]
SITE = 'https://www.uaart.com.ua'
PAGES = ('/video/index.html', '/video/seo/ua/kia-k5-koreya-kyiv.html', '/video/ua/UA-0013.html',
         '/video/podbor.html')
RUNS = 3
# Lighthouse 13 needs Node >= 22.19; 12.8.2 is the last release for older Node.
LIGHTHOUSE = ((22, 19), 'lighthouse@13.5.0', 'lighthouse@12.8.2')
CHROME_FLAGS = '--headless=new --no-sandbox --disable-dev-shm-usage'
RUN_TIMEOUT = 240
METRICS = {'first-contentful-paint': 'fcp_ms', 'largest-contentful-paint': 'lcp_ms', 'total-blocking-time': 'tbt_ms',
           'cumulative-layout-shift': 'cls', 'speed-index': 'si_ms'}
PASS_SCORE = 0.9
LCP_AUDITS = ('lcp-breakdown-insight', 'largest-contentful-paint-element')


class ProbeError(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def node_version(run=subprocess.run):
    out = run(['node', '--version'], capture_output=True, text=True, check=True, timeout=30).stdout.strip()
    match = re.fullmatch(r'v(\d+)\.(\d+)\.\d+', out)
    if not match:
        raise ProbeError('NODE_VERSION')
    return out, (int(match[1]), int(match[2]))


def package(version):
    minimum, current, legacy = LIGHTHOUSE
    return current if version >= minimum else legacy


def lighthouse(spec, url, run=subprocess.run):
    argv = ['npx', '--yes', spec, url, '--output=json', '--output-path=stdout', '--quiet',
            '--only-categories=performance,seo', '--form-factor=mobile', '--chrome-flags=' + CHROME_FLAGS]
    done = run(argv, capture_output=True, text=True, check=False, timeout=RUN_TIMEOUT)
    if done.returncode != 0:
        raise ProbeError('LIGHTHOUSE_EXIT:%d' % done.returncode)
    return json.loads(done.stdout)


def score(value):
    return None if value is None else round(value * 100)


def reduce(lhr):
    audits = lhr['audits']
    metrics = {}
    for audit, key in METRICS.items():
        value = audits.get(audit, {}).get('numericValue')
        metrics[key] = None if value is None else (round(value, 3) if key == 'cls' else round(value))
    failing = []
    for audit_id, audit in sorted(audits.items()):
        if audit_id in METRICS or audit.get('scoreDisplayMode') not in ('binary', 'numeric', 'metricSavings'):
            continue
        if audit.get('score') is not None and audit['score'] < PASS_SCORE:
            failing.append({'id': audit_id, 'title': audit.get('title', ''), 'display': audit.get('displayValue', ''),
                            'score': score(audit['score'])})
    lcp_node, lcp_parts = '', {}
    for audit_id in LCP_AUDITS:  # Lighthouse 13 insight, then the Lighthouse 12 audit
        for item in audits.get(audit_id, {}).get('details', {}).get('items', []):
            for row in item.get('items', [item]):
                node = row if row.get('type') == 'node' else row.get('node', {})
                lcp_node = lcp_node or node.get('snippet', '')[:300]
                if 'duration' in row and 'subpart' in row:
                    lcp_parts[row['subpart']] = round(row['duration'])
    categories = lhr['categories']
    return {'performance': score(categories['performance']['score']), 'seo': score(categories['seo']['score']),
            'metrics': metrics, 'failing': failing, 'lcp_element': lcp_node, 'lcp_parts_ms': lcp_parts,
            'final_url': lhr.get('finalDisplayedUrl') or lhr.get('finalUrl', ''),
            'runtime_error': (lhr.get('runtimeError') or {}).get('code', '')}


def median(results):
    ordered = sorted(results, key=lambda item: (item['performance'] is None, item['performance'] or 0))
    return ordered[len(ordered) // 2]


def collect(run=subprocess.run):
    node, version = node_version(run)
    spec = package(version)
    pages, environment = {}, {}
    for path in PAGES:
        results = []
        for _ in range(RUNS):
            lhr = lighthouse(spec, SITE + path, run)
            environment = environment or {'lighthouse': lhr.get('lighthouseVersion', ''),
                                          'user_agent': lhr.get('environment', {}).get('hostUserAgent', ''),
                                          'benchmark_index': lhr.get('environment', {}).get('benchmarkIndex')}
            results.append(reduce(lhr))
        chosen = median(results)
        pages[path] = {**chosen, 'runs_performance': [item['performance'] for item in results]}
    return {'node': node, 'package': spec, 'environment': environment, 'runs_per_page': RUNS,
            'preset': 'mobile (Lighthouse default: simulated slow 4G, 4x CPU slowdown)', 'pages': pages}


def validate_identity(env, root):
    if env.get('UAART_TASK_ID') not in TASKS or env.get('UAART_RECEIPT_PATH') != 'state/receipts/%s.json' % env.get('UAART_TASK_ID') \
            or env.get('UAART_REQUEST_PATH') != 'tasks/requests/%s.json' % env.get('UAART_TASK_ID'):
        raise ProbeError('IDENTITY')
    request = root / env['UAART_REQUEST_PATH']
    expected = env.get('UAART_REQUEST_SHA256', '')
    if sha(request.read_bytes()) != expected or not re.fullmatch(r'\d+', env.get('UAART_RUN_ID', '')):
        raise ProbeError('BINDING')
    raw = json.loads(request.read_bytes())
    if raw.get('read_only') is not True or raw.get('production_required') is not False:
        raise ProbeError('SCOPE')
    return expected, env['UAART_RUN_ID']


def write(root, relative, data):
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, 'xb') as handle:
        handle.write(data)


def dump(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def execute(env, *, root=None, run=subprocess.run):
    root = ROOT if root is None else Path(root)
    request_sha, run_id = validate_identity(env, root)
    task = env['UAART_TASK_ID']
    evidence = PACKAGE + '/evidence.json'
    write(root, evidence, dump({'task_id': task, 'run_id': run_id, 'remote_write_count': 0, **collect(run)}))
    receipt = {'task_id': task, 'status': 'FINISHED', 'task_class': 'STANDARD', 'target_environment': 'shadow',
               'live_source_environment': 'production', 'tests': 'PASS', 'tests_scope': 'READ_ONLY_PROBE',
               'unexpected_changes': 0, 'rollback_ready': True, 'rollback_ready_scope': 'NO_REMOTE_WRITES',
               'production_required': False, 'request_sha256': request_sha, 'run_id': run_id,
               'evidence_path': evidence}
    write(root, env['UAART_RECEIPT_PATH'], dump(receipt))
    return receipt


if __name__ == '__main__':
    try:
        execute(os.environ)
    except Exception as exc:
        print('PAGESPEED_PROBE_STOP:' + (str(exc) if isinstance(exc, ProbeError) else type(exc).__name__))
        raise SystemExit(1) from None
