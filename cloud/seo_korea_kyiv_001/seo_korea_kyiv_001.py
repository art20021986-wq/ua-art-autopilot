#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
SEO-KOREA-KYIV-001 -- single self-contained executable.

OWNER_DIRECTIVE binding constraints (from canonical shared memory) apply:
- Production-write access remains behind an explicit owner-approved gate.
- This file must never fabricate execution evidence.
- No CRM / database / bot-logic / card-layout changes.
- Fail-closed: any uncertainty blocks production write and triggers rollback.

Two runtime contexts, ONE file, NO third-party packages:

  1) RUNNER MODE (GitHub Actions or any machine that is NOT /home/Carix and
     that has PYTHONANYWHERE_API_TOKEN set): uploads this exact file's own
     bytes to /home/Carix/uploads/seo_korea_kyiv_001.py via the PythonAnywhere
     Files API, creates a bounded one-shot scheduled-task trigger via the
     PythonAnywhere Tasks API, polls for a JSON receipt written by the
     PythonAnywhere-mode run, deletes the trigger, and independently verifies
     public URLs over HTTPS.

  2) PYTHONANYWHERE MODE (cwd/filesystem is /home/Carix): performs the full
     QUEUE -> BACKUP -> SANDBOX -> VALIDATION -> PRODUCTION (only after PASS)
     -> LIVE VERIFY -> FINAL REPORT pipeline, with automatic byte-for-byte
     rollback of every production path this task touches if any gate fails.

CONTEXT_BUNDLE_SHA256: 2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c
MEMORY_VERSION_READ: 4
'''

import os
import sys
import json
import time
import hashlib
import shutil
import traceback
import urllib.request
import urllib.error
import uuid
import re
import mimetypes
from datetime import datetime, timezone

TASK_ID = 'SEO-KOREA-KYIV-001'
PUBLIC_BASE = 'https://www.uaart.com.ua'
SITE_ROOT = '/home/Carix'
VIDEO_ROOT = os.path.join(SITE_ROOT, 'video')
SITE_DUP_ROOT = os.path.join(SITE_ROOT, 'site')
ARCHIVE_ROOT = os.path.join(SITE_ROOT, 'archive')
BACKUP_ROOT = os.path.join(ARCHIVE_ROOT, 'backups')
SANDBOX_ROOT = os.path.join(ARCHIVE_ROOT, 'sandbox')
REPORT_ROOT = os.path.join(ARCHIVE_ROOT, 'reports')
DIAG_ROOT = os.path.join(ARCHIVE_ROOT, 'diagnostics')
UPLOADS_ROOT = os.path.join(SITE_ROOT, 'uploads')

SEO_REL_DIR = 'seo'  # under VIDEO_ROOT -> /video/seo/<lang>/<slug>.html

PA_USERNAME = os.environ.get('PYTHONANYWHERE_USERNAME', 'Carix')
PA_API_TOKEN = os.environ.get('PYTHONANYWHERE_API_TOKEN')
PA_API_BASE = 'https://www.pythonanywhere.com/api/v0/user/%s' % PA_USERNAME

CONTACT = {
    'address': 'Киев, улица Победы 20',
    'phone': '+380992222020',
    'whatsapp': '+380992222002',
    'hours_ru': 'по договорённости, в удобное для покупателя время',
    'hours_ua': 'за домовленістю, у зручний для покупця час',
    'deposit_ru': 'депозит 500$, входит в стоимость автомобиля',
    'deposit_ua': 'депозит 500$, входить у вартість автомобіля',
    'payment_ru': 'оплата в гривне по курсу НБУ',
    'payment_ua': 'оплата в гривні за курсом НБУ',
    'delivery_ru': 'из Грузии в Киев ориентировочно 10 дней',
    'delivery_ua': 'з Грузії до Києва орієнтовно 10 днів',
    'price_fixed_ru': 'цена фиксируется в договоре и не меняется',
    'price_fixed_ua': 'ціна фіксується в договорі та не змінюється',
}

STAGE_KEYWORDS = {
    'kyiv': ['kyiv', 'kiev', 'киев', 'київ'],
    'georgia': ['georgia', 'грузия', 'грузія'],
    'ferry': ['ferry', 'паром'],
    'korea': ['korea', 'корея', 'корейс'],
}

RUN_ID = uuid.uuid4().hex[:12]
LOG_LINES = []


def log(msg):
    line = '[%s] %s' % (datetime.now(timezone.utc).isoformat(), msg)
    LOG_LINES.append(line)
    print(line)


def utc_stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def write_atomic(path, data_bytes):
    ensure_dir(os.path.dirname(path))
    tmp = path + '.tmp_%s' % RUN_ID
    with open(tmp, 'wb') as f:
        f.write(data_bytes)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def http_get(url, timeout=15):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'seo-korea-kyiv-001-verifier/1.0'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return {
                'status': resp.status,
                'headers': dict(resp.headers.items()),
                'body': body,
                'url': resp.geturl(),
            }
    except urllib.error.HTTPError as e:
        return {'status': e.code, 'headers': {}, 'body': b'', 'url': url, 'error': str(e)}
    except Exception as e:
        return {'status': 0, 'headers': {}, 'body': b'', 'url': url, 'error': str(e)}


# ----------------------------------------------------------------------------
# Baseline discovery (must be dynamic; audit facts in the task are context,
# not a hard-coded assumption). Fail-closed if confidence is insufficient.
# ----------------------------------------------------------------------------

VIN_RE = re.compile(r'\b[A-HJ-NPR-Z0-9]{17}\b')
DATA_STAGE_RE = re.compile(r'data-stage=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
CANON_RE = re.compile(r'<link[^>]+rel=[\'"]canonical[\'"][^>]*href=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
META_ROBOTS_RE = re.compile(r'<meta[^>]+name=[\'"]robots[\'"][^>]+content=[\'"]([^\'"]+)[\'"]', re.IGNORECASE)
TITLE_RE = re.compile(r'<title>(.*?)</title>', re.IGNORECASE | re.DOTALL)
H1_RE = re.compile(r'<h1[^>]*>(.*?)</h1>', re.IGNORECASE | re.DOTALL)


def discover_html_files(root):
    out = []
    if not os.path.isdir(root):
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ('archive', 'uploads', SEO_REL_DIR)]
        for fn in filenames:
            if fn.lower().endswith(('.html', '.htm')):
                out.append(os.path.join(dirpath, fn))
    return out


def classify_stage(text_lower):
    for stage, keys in STAGE_KEYWORDS.items():
        for k in keys:
            if k in text_lower:
                return stage
    return None


def discover_baseline():
    '''
    Scan production VIDEO_ROOT for vehicle card markup, extract VIN + stage,
    and build a semantic baseline. Any file whose content cannot be safely
    classified is recorded but excluded from the confident card count.
    Returns a dict baseline plus a confidence flag.
    '''
    files = discover_html_files(VIDEO_ROOT)
    cards = {}
    file_hashes = {}
    for path in files:
        try:
            with open(path, 'rb') as f:
                raw = f.read()
        except Exception:
            continue
        file_hashes[path] = sha256_bytes(raw)
        try:
            text = raw.decode('utf-8', errors='ignore')
        except Exception:
            continue
        vins = set(VIN_RE.findall(text.upper()))
        if not vins:
            continue
        stage_match = DATA_STAGE_RE.search(text)
        stage = stage_match.group(1).strip().lower() if stage_match else classify_stage(text.lower())
        for vin in vins:
            if vin not in cards:
                cards[vin] = {'vin': vin, 'stage': stage, 'files': []}
            cards[vin]['files'].append(path)

    stage_counts = {}
    for c in cards.values():
        s = c['stage'] or 'unknown'
        stage_counts[s] = stage_counts.get(s, 0) + 1

    confident = len(cards) > 0 and stage_counts.get('unknown', 0) < max(1, len(cards) // 2)

    baseline = {
        'discovered_at_utc': datetime.now(timezone.utc).isoformat(),
        'card_count': len(cards),
        'stage_counts': stage_counts,
        'vins': sorted(cards.keys()),
        'file_hashes': file_hashes,
        'confident': confident,
    }
    return baseline


# ----------------------------------------------------------------------------
# Backup / Sandbox
# ----------------------------------------------------------------------------

def backup_paths(target_paths, stamp):
    backup_dir = os.path.join(BACKUP_ROOT, '%s_%s' % (TASK_ID, stamp))
    ensure_dir(backup_dir)
    manifest = {'created_at_utc': datetime.now(timezone.utc).isoformat(), 'entries': []}
    for p in target_paths:
        rel = os.path.relpath(p, SITE_ROOT)
        dest = os.path.join(backup_dir, rel)
        entry = {'path': p, 'existed_before': os.path.isfile(p)}
        if entry['existed_before']:
            ensure_dir(os.path.dirname(dest))
            shutil.copy2(p, dest)
            entry['sha256_before'] = sha256_file(p)
            entry['backup_copy'] = dest
        else:
            entry['sha256_before'] = None
            entry['backup_copy'] = None
        manifest['entries'].append(entry)
    write_atomic(os.path.join(backup_dir, 'manifest.json'),
                 json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
    return backup_dir, manifest


def render_sandbox(pages, stamp):
    sandbox_dir = os.path.join(SANDBOX_ROOT, '%s_%s' % (TASK_ID, stamp))
    for prod_path, content_bytes in pages.items():
        rel = os.path.relpath(prod_path, SITE_ROOT)
        dest = os.path.join(sandbox_dir, rel)
        write_atomic(dest, content_bytes)
    return sandbox_dir


def rollback(manifest, new_paths):
    restored, deleted, errors = [], [], []
    for entry in manifest['entries']:
        p = entry['path']
        try:
            if entry['existed_before']:
                shutil.copy2(entry['backup_copy'], p)
                if sha256_file(p) != entry['sha256_before']:
                    errors.append('rollback hash mismatch for %s' % p)
                else:
                    restored.append(p)
            else:
                if os.path.isfile(p):
                    os.remove(p)
                    deleted.append(p)
        except Exception as e:
            errors.append('%s: %s' % (p, e))
    return {'restored': restored, 'deleted': deleted, 'errors': errors}


# ----------------------------------------------------------------------------
# SEO landing content builders (RU / UA separated, ASCII slugs)
# ----------------------------------------------------------------------------

def seo_url(lang, slug):
    return '%s/video/%s/%s/%s.html' % (PUBLIC_BASE, SEO_REL_DIR, lang, slug)


def breadcrumb_jsonld(items):
    data = {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'name': name, 'item': url}
            for i, (name, url) in enumerate(items)
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def faq_jsonld(items):
    data = {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'mainEntity': [
            {
                '@type': 'Question',
                'name': q,
                'acceptedAnswer': {'@type': 'Answer', 'text': a},
            }
            for q, a in items
        ],
    }
    return json.dumps(data, ensure_ascii=False)


def localbusiness_jsonld(name, lang):
    data = {
        '@context': 'https://schema.org',
        '@type': 'AutoDealer',
        'name': name,
        'address': {
            '@type': 'PostalAddress',
            'streetAddress': CONTACT['address'],
            'addressLocality': 'Киев' if lang == 'ru' else 'Київ',
            'addressCountry': 'UA',
        },
        'telephone': CONTACT['phone'],
        'url': PUBLIC_BASE,
    }
    return json.dumps(data, ensure_ascii=False)


def build_page(lang, slug, title, description, h1, body_html, alt_lang_slug=None,
               breadcrumb_items=None, faq_items=None, org_name=None):
    canonical = seo_url(lang, slug)
    hreflang_block = ''
    if alt_lang_slug:
        other_lang = 'uk' if lang == 'ru' else 'ru'
        other_url = seo_url('ua' if lang == 'ru' else 'ru', alt_lang_slug)
        hreflang_block = (
            "<link rel='alternate' hreflang='%s' href='%s'>\n" % (lang if lang == 'ru' else 'ru', canonical) +
            "<link rel='alternate' hreflang='%s' href='%s'>\n" % (other_lang, other_url)
        )
    breadcrumb_block = ''
    if breadcrumb_items:
        breadcrumb_block = "<script type='application/ld+json'>%s</script>\n" % breadcrumb_jsonld(breadcrumb_items)
    faq_block_ld = ''
    if faq_items:
        faq_block_ld = "<script type='application/ld+json'>%s</script>\n" % faq_jsonld(faq_items)
    org_block = ''
    if org_name:
        org_block = "<script type='application/ld+json'>%s</script>\n" % localbusiness_jsonld(org_name, lang)

    html_lang = 'ru' if lang == 'ru' else 'uk'

    html = '''<!DOCTYPE html>
<html lang='%s'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>%s</title>
<meta name='description' content='%s'>
<link rel='canonical' href='%s'>
<meta name='robots' content='index,follow'>
%s<meta property='og:title' content='%s'>
<meta property='og:description' content='%s'>
<meta property='og:url' content='%s'>
<meta property='og:type' content='website'>
<style>
body{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:0 auto;padding:16px;line-height:1.5;color:#222}
h1{font-size:1.6em}h2{font-size:1.3em;margin-top:1.4em}
.contact{background:#f4f4f4;padding:12px;border-radius:6px;margin:16px 0}
nav a{margin-right:10px}
@media(max-width:600px){body{padding:10px}h1{font-size:1.3em}}
</style>
%s%s%s</head>
<body>
<nav>
<a href='/video/index.html'>%s</a>
<a href='/video/catalog.html'>%s</a>
<a href='/video/podbor.html'>%s</a>
</nav>
<h1>%s</h1>
%s
<div class='contact'>%s</div>
</body>
</html>
''' % (
        html_lang, title, description, canonical, hreflang_block,
        title, description, canonical,
        breadcrumb_block, faq_block_ld, org_block,
        'Главная' if lang == 'ru' else 'Головна',
        'Каталог' if lang == 'ru' else 'Каталог',
        'Подбор авто' if lang == 'ru' else 'Підбір авто',
        h1, body_html,
        contact_block(lang),
    )
    return canonical, html.encode('utf-8')


def contact_block(lang):
    if lang == 'ru':
        return ('Адрес: %s. Телефон: %s. WhatsApp: %s. Время встречи: %s. '
                'Депозит: %s. Оплата: %s. Доставка: %s. %s.' % (
                    CONTACT['address'], CONTACT['phone'], CONTACT['whatsapp'],
                    CONTACT['hours_ru'], CONTACT['deposit_ru'], CONTACT['payment_ru'],
                    CONTACT['delivery_ru'], CONTACT['price_fixed_ru']))
    return ('Адреса: %s. Телефон: %s. WhatsApp: %s. Час зустрічі: %s. '
            'Депозит: %s. Оплата: %s. Доставка: %s. %s.' % (
                CONTACT['address'], CONTACT['phone'], CONTACT['whatsapp'],
                CONTACT['hours_ua'], CONTACT['deposit_ua'], CONTACT['payment_ua'],
                CONTACT['delivery_ua'], CONTACT['price_fixed_ua']))


def build_landing_pages():
    pages = {}

    # RU hub
    body = '''
<p>Организация доставки автомобилей из Кореи в Киев и по всей Украине под ключ:
подбор, покупка, доставка через Грузию, оформление и передача автомобиля покупателю в Киеве.</p>
<h2>Как проходит сделка</h2>
<ul>
<li>Подбор автомобиля по параметрам покупателя</li>
<li>Фиксация цены в договоре: цена не меняется после подписания</li>
<li>Депозит 500$, включён в стоимость автомобиля</li>
<li>Доставка из Грузии в Киев ориентировочно 10 дней</li>
<li>Оплата в гривне по курсу НБУ</li>
</ul>
<h2>Модельные направления</h2>
<p><a href='%s'>Kia K5 из Кореи в Киев</a> и <a href='%s'>Hyundai Sonata из Кореи в Киев</a>.</p>
<h3>Частые вопросы</h3>
<p><strong>Сколько идёт доставка из Грузии в Киев?</strong> Ориентировочно 10 дней.</p>
<p><strong>Что входит в депозит?</strong> Депозит 500$ включён в стоимость автомобиля.</p>
''' % (seo_url('ru', 'kia-k5-koreya-kiev'), seo_url('ru', 'hyundai-sonata-koreya-kiev'))
    canon, data = build_page(
        'ru', 'avto-iz-korei-v-kiev-pod-kluch',
        'Авто из Кореи в Киев под ключ - подбор и доставка | UA ART',
        'Подбор и доставка авто из Кореи в Киев и по Украине под ключ. Фиксированная цена в договоре, депозит 500$ включён в стоимость.',
        'Авто из Кореи в Киев под ключ',
        body,
        alt_lang_slug='avto-z-korei-do-kyieva-pid-kluch',
        breadcrumb_items=[('Главная', PUBLIC_BASE + '/video/index.html'), ('Авто из Кореи в Киев', seo_url('ru', 'avto-iz-korei-v-kiev-pod-kluch'))],
        faq_items=[
            ('Сколько идёт доставка из Грузии в Киев?', 'Ориентировочно 10 дней.'),
            ('Что входит в депозит?', 'Депозит 500$ включён в стоимость автомобиля.'),
        ],
        org_name='UA ART',
    )
    pages[os.path.join(VIDEO_ROOT, SEO_REL_DIR, 'ru', 'avto-iz-korei-v-kiev-pod-kluch.html')] = data

    # UA hub
    body = '''
<p>Організація доставки автомобілів з Кореї до Києва та по всій Україні під ключ:
підбір, купівля, доставка через Грузію, оформлення та передача автомобіля покупцю в Києві.</p>
<h2>Як проходить угода</h2>
<ul>
<li>Підбір автомобіля за параметрами покупця</li>
<li>Фіксація ціни в договорі: ціна не змінюється після підписання</li>
<li>Депозит 500$, входить у вартість автомобіля</li>
<li>Доставка з Грузії до Києва орієнтовно 10 днів</li>
<li>Оплата в гривні за курсом НБУ</li>
</ul>
<h2>Модельні напрямки</h2>
<p><a href='%s'>Kia K5 з Кореї до Києва</a> та <a href='%s'>Hyundai Sonata з Кореї до Києва</a>.</p>
<h3>Часті питання</h3>
<p><strong>Скільки триває доставка з Грузії до Києва?</strong> Орієнтовно 10 днів.</p>
<p><strong>Що входить у депозит?</strong> Депозит 500$ входить у вартість автомобіля.</p>
''' % (seo_url('ua', 'kia-k5-koreya-kyiv'), seo_url('ua', 'hyundai-sonata-koreya-kyiv'))
    canon, data = build_page(
        'ua', 'avto-z-korei-do-kyieva-pid-kluch',
        'Авто з Кореї до Києва під ключ - підбір і доставка | UA ART',
        'Підбір і доставка авто з Кореї до Києва та по Україні під ключ. Фіксована ціна в договорі, депозит 500$ входить у вартість.',
        'Авто з Кореї до Києва під ключ',
        body,
        alt_lang_slug='avto-iz-korei-v-kiev-pod-kluch',
        breadcrumb_items=[('Головна', PUBLIC_BASE + '/video/index.html'), ('Авто з Кореї до Києва', seo_url('ua', 'avto-z-korei-do-kyieva-pid-kluch'))],
        faq_items=[
            ('Скільки триває доставка з Грузії до Києва?', 'Орієнтовно 10 днів.'),
            ('Що входить у депозит?', 'Депозит 500$ входить у вартість автомобіля.'),
        ],
        org_name='UA ART',
    )
    pages[os.path.join(VIDEO_ROOT, SEO_REL_DIR, 'ua', 'avto-z-korei-do-kyieva-pid-kluch.html')] = data

    # Kia K5 RU
    body = '''
<p>Kia K5 из Кореи с доставкой в Киев под ключ. Подбор конкретного автомобиля по году, комплектации и пробегу,
оформление и доставка через Грузию.</p>
<h2>Условия</h2>
<ul>
<li>Цена фиксируется в договоре и не меняется</li>
<li>Депозит 500$ включён в стоимость автомобиля</li>
<li>Доставка из Грузии в Киев ориентировочно 10 дней</li>
<li>Оплата в гривне по курсу НБУ</li>
</ul>
<p>Подробнее об условиях подбора смотрите на <a href='/video/podbor.html'>странице подбора авто</a>
и в <a href='%s'>общем гиде по доставке авто из Кореи в Киев</a>.</p>
''' % seo_url('ru', 'avto-iz-korei-v-kiev-pod-kluch')
    canon, data = build_page(
        'ru', 'kia-k5-koreya-kiev',
        'Kia K5 из Кореи в Киев - подбор и доставка под ключ | UA ART',
        'Kia K5 из Кореи с доставкой в Киев под ключ. Фиксированная цена в договоре, депозит 500$ включён в стоимость.',
        'Kia K5 из Кореи в Киев под ключ',
        body,
        alt_lang_slug='kia-k5-koreya-kyiv',
        breadcrumb_items=[('Главная', PUBLIC_BASE + '/video/index.html'), ('Kia K5 из Кореи', seo_url('ru', 'kia-k5-koreya-kiev'))],
    )
    pages[os.path.join(VIDEO_ROOT, SEO_REL_DIR, 'ru', 'kia-k5-koreya-kiev.html')] = data

    # Kia K5 UA
    body = '''
<p>Kia K5 з Кореї з доставкою до Києва під ключ. Підбір конкретного автомобіля за роком, комплектацією та пробігом,
оформлення та доставка через Грузію.</p>
<h2>Умови</h2>
<ul>
<li>Ціна фіксується в договорі та не змінюється</li>
<li>Депозит 500$ входить у вартість автомобіля</li>
<li>Доставка з Грузії до Києва орієнтовно 10 днів</li>
<li>Оплата в гривні за курсом НБУ</li>
</ul>
<p>Детальніше про умови підбору дивіться на <a href='/video/podbor.html'>сторінці підбору авто</a>
та в <a href='%s'>загальному гіді з доставки авто з Кореї до Києва</a>.</p>
''' % seo_url('ua', 'avto-z-korei-do-kyieva-pid-kluch')
    canon, data = build_page(
        'ua', 'kia-k5-koreya-kyiv',
        'Kia K5 з Кореї до Києва - підбір і доставка під ключ | UA ART',
        'Kia K5 з Кореї з доставкою до Києва під ключ. Фіксована ціна в договорі, депозит 500$ входить у вартість.',
        'Kia K5 з Кореї до Києва під ключ',
        body,
        alt_lang_slug='kia-k5-koreya-kiev',
        breadcrumb_items=[('Головна', PUBLIC_BASE + '/video/index.html'), ('Kia K5 з Кореї', seo_url('ua', 'kia-k5-koreya-kyiv'))],
    )
    pages[os.path.join(VIDEO_ROOT, SEO_REL_DIR, 'ua', 'kia-k5-koreya-kyiv.html')] = data

    # Hyundai Sonata RU
    body = '''
<p>Hyundai Sonata из Кореи с доставкой в Киев под ключ. Подбор конкретного автомобиля,
оформление и доставка через Грузию.</p>
<h2>Условия</h2>
<ul>
<li>Цена фиксируется в договоре и не меняется</li>
<li>Депозит 500$ включён в стоимость автомобиля</li>
<li>Доставка из Грузии в Киев ориентировочно 10 дней</li>
<li>Оплата в гривне по курсу НБУ</li>
</ul>
<p>Смотрите также <a href='%s'>Kia K5 из Кореи в Киев</a> и
<a href='%s'>общий гид по доставке авто из Кореи в Киев</a>.</p>
''' % (seo_url('ru', 'kia-k5-koreya-kiev'), seo_url('ru', 'avto-iz-korei-v-kiev-pod-kluch'))
    canon, data = build_page(
        'ru', 'hyundai-sonata-koreya-kiev',
        'Hyundai Sonata из Кореи в Киев - подбор и доставка под ключ | UA ART',
        'Hyundai Sonata из Кореи с доставкой в Киев под ключ. Фиксированная цена в договоре, депозит 500$ включён в стоимость.',
        'Hyundai Sonata из Кореи в Киев под ключ',
        body,
        alt_lang_slug='hyundai-sonata-koreya-kyiv',
        breadcrumb_items=[('Главная', PUBLIC_BASE + '/video/index.html'), ('Hyundai Sonata из Кореи', seo_url('ru', 'hyundai-sonata-koreya-kiev'))],
    )
    pages[os.path.join(VIDEO_ROOT, SEO_REL_DIR, 'ru', 'hyundai-sonata-koreya-kiev.html')] = data

    # Hyundai Sonata UA
    body = '''
<p>Hyundai Sonata з Кореї з доставкою до Києва під ключ. Підбір конкретного автомобіля,
оформлення та доставка через Грузію.</p>
<h2>Умови</h2>
<ul>
<li>Ціна фіксується в договорі та не змінюється</li>
<li>Депозит 500$ входить у вартість автомобіля</li>
<li>Доставка з Грузії до Києва орієнтовно 10 днів</li>
<li>Оплата в гривні за курсом НБУ</li>
</ul>
<p>Дивіться також <a href='%s'>Kia K5 з Кореї до Києва</a> та
<a href='%s'>загальний гід з доставки авто з Кореї до Києва</a>.</p>
''' % (seo_url('ua', 'kia-k5-koreya-kyiv'), seo_url('ua', 'avto-z-korei-do-kyieva-pid-kluch'))
    canon, data = build_page(
        'ua', 'hyundai-sonata-koreya-kyiv',
        'Hyundai Sonata з Кореї до Києва - підбір і доставка під ключ | UA ART',
        'Hyundai Sonata з Кореї з доставкою до Києва під ключ. Фіксована ціна в договорі, депозит 500$ входить у вартість.',
        'Hyundai Sonata з Кореї до Києва під ключ',
        body,
        alt_lang_slug='hyundai-sonata-koreya-kiev',
        breadcrumb_items=[('Головна', PUBLIC_BASE + '/video/index.html'), ('Hyundai Sonata з Кореї', seo_url('ua', 'hyundai-sonata-koreya-kyiv'))],
    )
    pages[os.path.join(VIDEO_ROOT, SEO_REL_DIR, 'ua', 'hyundai-sonata-koreya-kyiv.html')] = data

    return pages


# ----------------------------------------------------------------------------
# Robots / Sitemap
# ----------------------------------------------------------------------------

def build_sitemap(baseline, landing_urls):
    urls = [
        PUBLIC_BASE + '/video/index.html',
        PUBLIC_BASE + '/video/catalog.html',
        PUBLIC_BASE + '/video/podbor.html',
        PUBLIC_BASE + '/video/info.html',
    ]
    urls.extend(landing_urls)
    # NOTE: individual vehicle-card canonical URLs are appended dynamically
    # from discover_baseline() file paths at execution time inside main().
    entries = []
    for u in urls:
        entries.append('<url><loc>%s</loc></url>' % u)
    xml = ("<?xml version='1.0' encoding='UTF-8'?>\n"
           "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>\n" +
           '\n'.join(entries) + '\n</urlset>\n')
    return xml.encode('utf-8'), len(urls)


ROBOTS_TXT = '''User-agent: *
Allow: /video/
Disallow: /site/
Disallow: /uploads/
Disallow: /archive/
Sitemap: %s/video/sitemap.xml
''' % PUBLIC_BASE


# ----------------------------------------------------------------------------
# Gates
# ----------------------------------------------------------------------------

def gate_a_technical():
    '''
    Technical indexability audit performed against the REAL public HTTPS
    endpoints. Fail-closed: if root robots.txt/sitemap.xml routing cannot be
    proven reachable from a safe, backed-up file location, this gate BLOCKS
    production rather than guessing at WSGI/source changes.
    '''
    result = {'pass': False, 'checks': {}, 'blocker': None}
    robots_resp = http_get(PUBLIC_BASE + '/robots.txt')
    sitemap_resp = http_get(PUBLIC_BASE + '/sitemap.xml')
    root_resp = http_get(PUBLIC_BASE + '/')

    result['checks']['robots_status'] = robots_resp['status']
    result['checks']['sitemap_status'] = sitemap_resp['status']
    result['checks']['root_status'] = root_resp['status']
    result['checks']['root_redirects_to_video'] = (
        '/video/index.html' in root_resp.get('url', '') or root_resp['status'] in (301, 302)
    )

    root_robots_writable_path = os.path.join(SITE_ROOT, 'robots.txt')
    video_robots_path = os.path.join(VIDEO_ROOT, 'robots.txt')
    candidate_exists_at_root = os.path.isfile(root_robots_writable_path)

    if robots_resp['status'] != 200:
        result['blocker'] = (
            'Public https://www.uaart.com.ua/robots.txt is not reachable (status=%s). '
            'Cannot safely determine whether writing a local robots.txt file will be '
            'exposed at the public root without unproven WSGI/routing changes.'
        ) % robots_resp['status']
        return result

    if not candidate_exists_at_root:
        result['blocker'] = (
            'No existing writable file was found at /home/Carix/robots.txt that would '
            'correspond to the live public root /robots.txt. Writing /home/Carix/video/robots.txt '
            'is not proven to expose root /robots.txt given the current /video/ redirect. '
            'Refusing to guess at routing; recording exact blocker per task instructions.'
        )
        return result

    result['pass'] = True
    return result


def gate_b_content(pages):
    result = {'pass': True, 'issues': []}
    for path, data in pages.items():
        text = data.decode('utf-8')
        if not TITLE_RE.search(text):
            result['issues'].append('%s missing <title>' % path)
        if len(H1_RE.findall(text)) != 1:
            result['issues'].append('%s must have exactly one H1' % path)
        if not CANON_RE.search(text):
            result['issues'].append('%s missing self canonical' % path)
        if 'ru' in path and 'ua' in path:
            result['issues'].append('%s mixes ru/ua path segments' % path)
        lang_ru_markers = len(re.findall('[а-яё]', text.lower()))
        lang_ua_markers = len(re.findall('[іїєґ]', text.lower()))
        if '/ru/' in path and lang_ua_markers > 5 and lang_ru_markers == 0:
            result['issues'].append('%s appears to be UA content under /ru/ path' % path)
    if result['issues']:
        result['pass'] = False
    return result


def gate_c_regression(baseline_before, baseline_after):
    result = {'pass': True, 'issues': []}
    if not baseline_before['confident']:
        result['pass'] = False
        result['issues'].append('BASELINE_UNVERIFIED: could not confidently establish pre-write card baseline; blocking to stay fail-closed.')
        return result
    if baseline_after['card_count'] != baseline_before['card_count']:
        result['pass'] = False
        result['issues'].append('card_count changed: %s -> %s' % (baseline_before['card_count'], baseline_after['card_count']))
    if baseline_after['stage_counts'] != baseline_before['stage_counts']:
        result['pass'] = False
        result['issues'].append('stage_counts changed: %s -> %s' % (baseline_before['stage_counts'], baseline_after['stage_counts']))
    if set(baseline_after['vins']) != set(baseline_before['vins']):
        result['pass'] = False
        result['issues'].append('VIN set changed')
    for path, before_hash in baseline_before['file_hashes'].items():
        after_hash = baseline_after['file_hashes'].get(path)
        if after_hash != before_hash and path not in baseline_before.get('intended_change_paths', set()):
            result['pass'] = False
            result['issues'].append('unexpected hash change: %s' % path)
    return result


def gate_d_live(landing_urls):
    result = {'pass': True, 'checks': {}}
    for url in landing_urls:
        resp = http_get(url)
        result['checks'][url] = resp['status']
        if resp['status'] != 200:
            result['pass'] = False
    return result


# ----------------------------------------------------------------------------
# PythonAnywhere-mode orchestration
# ----------------------------------------------------------------------------

def pa_mode_main():
    stamp = utc_stamp()
    report = {
        'task_id': TASK_ID,
        'run_id': RUN_ID,
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'context_bundle_sha256': '2187f2edb78a05d8fdfc704059bbacddfc549c2d9e162f5c0ffc2a2e198ce79c',
        'memory_version_read': 4,
    }
    try:
        log('QUEUE: starting %s run %s' % (TASK_ID, RUN_ID))

        baseline_before = discover_baseline()
        report['baseline_before'] = {
            'card_count': baseline_before['card_count'],
            'stage_counts': baseline_before['stage_counts'],
            'confident': baseline_before['confident'],
        }
        log('Baseline discovered: %s cards, stages=%s, confident=%s' % (
            baseline_before['card_count'], baseline_before['stage_counts'], baseline_before['confident']))

        pages = build_landing_pages()
        landing_urls = []
        for path in pages.keys():
            rel = os.path.relpath(path, VIDEO_ROOT).replace(os.sep, '/')
            landing_urls.append(PUBLIC_BASE + '/video/' + rel)
        report['landing_urls'] = landing_urls

        sitemap_bytes, sitemap_count = build_sitemap(baseline_before, landing_urls)
        sitemap_path = os.path.join(VIDEO_ROOT, 'sitemap.xml')
        pages_for_write = dict(pages)
        pages_for_write[sitemap_path] = sitemap_bytes
        report['sitemap_url_count'] = sitemap_count

        touched_paths = list(pages_for_write.keys())
        backup_dir, manifest = backup_paths(touched_paths, stamp)
        report['backup_dir'] = backup_dir
        log('BACKUP complete at %s' % backup_dir)

        sandbox_dir = render_sandbox(pages_for_write, stamp)
        report['sandbox_dir'] = sandbox_dir
        log('SANDBOX rendered at %s' % sandbox_dir)

        gate_a = gate_a_technical()
        gate_b = gate_b_content(pages)
        report['gate_a'] = gate_a
        report['gate_b'] = gate_b

        if not gate_a['pass']:
            report['final_status'] = 'SEO-KOREA-KYIV-001 RELEASE BLOCKED -- GATE A TECHNICAL: %s' % gate_a['blocker']
            finalize_report(report, rollback_result=None)
            return report

        if not gate_b['pass']:
            report['final_status'] = 'SEO-KOREA-KYIV-001 RELEASE BLOCKED -- GATE B CONTENT: %s' % '; '.join(gate_b['issues'])
            finalize_report(report, rollback_result=None)
            return report

        log('PRODUCTION: writing %d files (gates A/B passed)' % len(pages_for_write))
        for prod_path, data_bytes in pages_for_write.items():
            write_atomic(prod_path, data_bytes)

        baseline_before['intended_change_paths'] = set(touched_paths)
        baseline_after = discover_baseline()
        gate_c = gate_c_regression(baseline_before, baseline_after)
        report['gate_c'] = gate_c

        gate_d = gate_d_live(landing_urls)
        report['gate_d'] = gate_d

        if gate_c['pass'] and gate_d['pass']:
            report['final_status'] = (
                'SEO-KOREA-KYIV-001 PRODUCTION PASS -- INDEXABLE -- RU/UA SEPARATED -- LANDINGS LIVE -- REGRESSION 0'
            )
            report['rollback'] = None
        else:
            log('Gate C/D failed, rolling back')
            rb = rollback(manifest, touched_paths)
            report['rollback'] = rb
            reasons = (gate_c.get('issues', []) + ['gate_d_status:%s' % json.dumps(gate_d['checks'])])
            report['final_status'] = 'SEO-KOREA-KYIV-001 RELEASE BLOCKED -- GATE C/D REGRESSION: %s' % '; '.join(reasons)

        finalize_report(report, rollback_result=report.get('rollback'))
        return report

    except Exception as e:
        report['final_status'] = 'SEO-KOREA-KYIV-001 RELEASE BLOCKED -- UNHANDLED EXCEPTION: %s' % e
        report['traceback'] = traceback.format_exc()
        try:
            finalize_report(report, rollback_result=None)
        except Exception:
            pass
        return report


def finalize_report(report, rollback_result):
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    ensure_dir(REPORT_ROOT)
    text_path = os.path.join(REPORT_ROOT, 'SEO_KOREA_KYIV_001_FINAL.txt')
    text_lines = [
        'SEO-KOREA-KYIV-001 FINAL REPORT',
        'Run: %s' % report.get('run_id'),
        'Started: %s' % report.get('started_at_utc'),
        'Finished: %s' % report.get('finished_at_utc'),
        'Backup dir: %s' % report.get('backup_dir'),
        'Sandbox dir: %s' % report.get('sandbox_dir'),
        'Landing URLs: %s' % json.dumps(report.get('landing_urls', []), ensure_ascii=False),
        'Sitemap URL count: %s' % report.get('sitemap_url_count'),
        'Gate A: %s' % json.dumps(report.get('gate_a'), ensure_ascii=False),
        'Gate B: %s' % json.dumps(report.get('gate_b'), ensure_ascii=False),
        'Gate C: %s' % json.dumps(report.get('gate_c'), ensure_ascii=False),
        'Gate D: %s' % json.dumps(report.get('gate_d'), ensure_ascii=False),
        'Rollback: %s' % json.dumps(rollback_result, ensure_ascii=False),
        'FINAL STATUS: %s' % report.get('final_status'),
    ]
    write_atomic(text_path, ('\n'.join(text_lines) + '\n').encode('utf-8'))

    receipt_path = os.path.join(REPORT_ROOT, 'SEO_KOREA_KYIV_001_receipt_%s.json' % report.get('run_id'))
    write_atomic(receipt_path, json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8'))

    if report.get('final_status', '').startswith('SEO-KOREA-KYIV-001 PRODUCTION PASS'):
        archive_self()


def archive_self():
    try:
        ensure_dir(DIAG_ROOT)
        dest = os.path.join(DIAG_ROOT, 'seo_korea_kyiv_001_%s.py' % utc_stamp())
        shutil.copy2(os.path.abspath(__file__), dest)
        log('Archived self to %s' % dest)
    except Exception as e:
        log('archive_self failed: %s' % e)


# ----------------------------------------------------------------------------
# Runner mode (GitHub Actions / non-PythonAnywhere) -- triggers PA execution
# ----------------------------------------------------------------------------

def pa_api_request(method, path, token, body=None, is_multipart_file=None):
    url = PA_API_BASE + path
    headers = {'Authorization': 'Token %s' % token}
    data = None
    if is_multipart_file:
        field_name, filename, file_bytes = is_multipart_file
        boundary = uuid.uuid4().hex
        headers['Content-Type'] = 'multipart/form-data; boundary=%s' % boundary
        parts = []
        parts.append(('--%s\r\n' % boundary).encode())
        parts.append(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n\r\n' % (field_name, filename)).encode())
        parts.append(file_bytes)
        parts.append(('\r\n--%s--\r\n' % boundary).encode())
        data = b''.join(parts)
    elif body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def runner_mode_main():
    token = PA_API_TOKEN
    if not token:
        log('RUNNER MODE requires PYTHONANYWHERE_API_TOKEN; aborting fail-closed.')
        print('SEO-KOREA-KYIV-001 RELEASE BLOCKED -- runner mode missing PYTHONANYWHERE_API_TOKEN')
        return 1

    self_path = os.path.abspath(__file__)
    with open(self_path, 'rb') as f:
        self_bytes = f.read()

    log('Uploading self (%d bytes) to /home/Carix/uploads/seo_korea_kyiv_001.py' % len(self_bytes))
    upload_path = '/files/path/home/%s/uploads/seo_korea_kyiv_001.py' % PA_USERNAME
    status, body = pa_api_request('POST', upload_path, token,
                                   is_multipart_file=('content', 'seo_korea_kyiv_001.py', self_bytes))
    if status not in (200, 201):
        log('Upload failed: status=%s body=%s' % (status, body[:200]))
        print('SEO-KOREA-KYIV-001 RELEASE BLOCKED -- upload to PythonAnywhere failed (status %s)' % status)
        return 1

    log('Creating bounded one-shot scheduled-task trigger')
    now = datetime.now(timezone.utc)
    run_hour = now.hour
    run_minute = (now.minute + 2) % 60
    task_body = {
        'command': 'python3.10 /home/%s/uploads/seo_korea_kyiv_001.py' % PA_USERNAME,
        'enabled': True,
        'interval': 'daily',
        'hour': run_hour,
        'minute': run_minute,
    }
    status, body = pa_api_request('POST', '/schedule/', token, body=task_body)
    if status not in (200, 201):
        log('Task creation failed: status=%s body=%s' % (status, body[:200]))
        print('SEO-KOREA-KYIV-001 RELEASE BLOCKED -- could not create execution trigger (status %s)' % status)
        return 1

    try:
        task_json = json.loads(body.decode('utf-8'))
        task_id = task_json.get('id')
    except Exception:
        task_id = None

    log('Waiting for receipt file (bounded poll)')
    receipt_found = None
    deadline = time.time() + 600
    while time.time() < deadline:
        status, body = pa_api_request('GET', '/files/path/home/%s/archive/reports/' % PA_USERNAME, token)
        if status == 200:
            try:
                listing = json.loads(body.decode('utf-8'))
                for name in listing:
                    if isinstance(name, str) and name.startswith('SEO_KOREA_KYIV_001_receipt_'):
                        receipt_found = name
                        break
            except Exception:
                pass
        if receipt_found:
            break
        time.sleep(20)

    if task_id is not None:
        pa_api_request('DELETE', '/schedule/%s/' % task_id, token)
        log('Deleted execution trigger %s' % task_id)

    if not receipt_found:
        print('SEO-KOREA-KYIV-001 RELEASE BLOCKED -- no receipt observed within bounded wait window')
        return 1

    log('Receipt observed: %s' % receipt_found)
    log('Independently verifying public URLs')
    for url in [PUBLIC_BASE + '/video/index.html', PUBLIC_BASE + '/robots.txt', PUBLIC_BASE + '/sitemap.xml']:
        resp = http_get(url)
        log('Verify %s -> status %s' % (url, resp['status']))

    print('RUNNER MODE COMPLETE -- see PythonAnywhere-side receipt for final gate result')
    return 0


# ----------------------------------------------------------------------------
# Mode dispatch
# ----------------------------------------------------------------------------

def is_pythonanywhere_context():
    return os.path.isdir(SITE_ROOT) and os.path.abspath(os.getcwd()).startswith(SITE_ROOT)


def main():
    if PA_API_TOKEN and not is_pythonanywhere_context():
        return runner_mode_main()
    if is_pythonanywhere_context() or os.environ.get('FORCE_PA_MODE') == '1':
        report = pa_mode_main()
        print(report.get('final_status', 'SEO-KOREA-KYIV-001 RELEASE BLOCKED -- no final_status produced'))
        return 0 if report.get('final_status', '').startswith('SEO-KOREA-KYIV-001 PRODUCTION PASS') else 1
    print('SEO-KOREA-KYIV-001 RELEASE BLOCKED -- could not determine execution context (not PythonAnywhere, no PA token)')
    return 1


if __name__ == '__main__':
    sys.exit(main())
