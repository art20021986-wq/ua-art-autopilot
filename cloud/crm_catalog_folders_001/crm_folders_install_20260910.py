#!/usr/bin/env python3
"""Install only the CRM folder adapter. Default: read-only preflight."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

ROOT = Path('/home/Carix')
SOURCE = ROOT / 'cars_ui.py'
CORE = ROOT / 'ua_crm_catalog_folders.py'
EXPECTED = '2c79fffff4cad8a23cb3f8992190ff03c17210655ddd374e9548d6e88563a246'
MARKER = b'# UA-ART-CRM-CATALOG-FOLDERS-001:START'
CORE_TEXT = '"""Read-only grouping by the completed catalog HTML, never publication intent.\n\nThe integration must supply the complete authorized CRM list and the catalog\nbytes from its existing committed local publication path. This module performs\nno database, filesystem, HTTP, publication, or status writes.\n"""\nfrom html.parser import HTMLParser\nimport re\nfrom typing import Any, Iterable, Mapping\n\n\n_CAR_NUMBER = re.compile(r"UA-[0-9]{4,}\\Z")\n_BRAND = re.compile(r"\\bUA\\s+ART\\b", re.IGNORECASE)\n_STRUCTURAL = frozenset(("html", "head", "body", "title"))\n\n\nclass CatalogSnapshotError(ValueError):\n    """The supplied catalog/CRM snapshot cannot be classified unambiguously."""\n\n\ndef _valid_number(value: Any) -> bool:\n    return isinstance(value, str) and _CAR_NUMBER.fullmatch(value) is not None\n\n\nclass _CatalogParser(HTMLParser):\n    def __init__(self) -> None:\n        super().__init__(convert_charrefs=True)\n        self.stack = []\n        self.seen = set()\n        self.closed_html = False\n        self.title_parts = []\n        self.numbers = set()\n\n    def handle_starttag(self, tag, attrs):\n        if tag == "html":\n            if self.stack or "html" in self.seen or self.closed_html:\n                raise CatalogSnapshotError("Catalog must contain exactly one HTML document")\n        elif not self.stack or self.closed_html:\n            raise CatalogSnapshotError("Element outside the catalog HTML document")\n        if tag in _STRUCTURAL:\n            if tag in self.seen:\n                raise CatalogSnapshotError("Duplicate catalog structural element: " + tag)\n            if tag in ("head", "body") and self.stack != ["html"]:\n                raise CatalogSnapshotError("Invalid catalog structural nesting")\n            if tag == "head" and "body" in self.seen:\n                raise CatalogSnapshotError("Catalog head follows body")\n            if tag == "title" and self.stack not in (["html"], ["html", "head"]):\n                raise CatalogSnapshotError("Invalid catalog title location")\n            self.stack.append(tag)\n            self.seen.add(tag)\n        if "title" in self.stack and tag != "title":\n            raise CatalogSnapshotError("Markup inside catalog title")\n        markers = [value for key, value in attrs if key == "data-ua-card"]\n        if len(markers) > 1:\n            raise CatalogSnapshotError("Duplicate data-ua-card attribute")\n        if markers:\n            number = markers[0]\n            if not _valid_number(number):\n                raise CatalogSnapshotError("Invalid catalog car number")\n            if number in self.numbers:\n                raise CatalogSnapshotError("Duplicate catalog car number: " + number)\n            self.numbers.add(number)\n\n    def handle_endtag(self, tag):\n        if not self.stack or self.closed_html:\n            raise CatalogSnapshotError("Closing element outside catalog HTML")\n        if tag in _STRUCTURAL:\n            if self.stack[-1] != tag:\n                raise CatalogSnapshotError("Incomplete or misnested catalog document")\n            self.stack.pop()\n            if tag == "html":\n                self.closed_html = True\n\n    def handle_startendtag(self, tag, attrs):\n        if tag in _STRUCTURAL:\n            raise CatalogSnapshotError("Self-closing catalog structural element")\n        self.handle_starttag(tag, attrs)\n\n    def handle_data(self, data):\n        if (not self.stack or self.closed_html) and data.strip():\n            raise CatalogSnapshotError("Text outside catalog HTML document")\n        if self.stack and self.stack[-1] == "title":\n            self.title_parts.append(data)\n\n    def result(self) -> frozenset[str]:\n        if not self.closed_html or self.stack or "title" not in self.seen:\n            raise CatalogSnapshotError("Incomplete catalog HTML document")\n        if _BRAND.search("".join(self.title_parts)) is None:\n            raise CatalogSnapshotError("Catalog title does not identify UA ART")\n        return frozenset(self.numbers)\n\n\ndef parse_catalog(source: str) -> frozenset[str]:\n    """Extract unique canonical numbers from a complete UA ART HTML document."""\n    if not isinstance(source, str) or not source.strip():\n        raise CatalogSnapshotError("Missing catalog HTML")\n    parser = _CatalogParser()\n    try:\n        parser.feed(source)\n        parser.close()\n    except CatalogSnapshotError:\n        raise\n    except (ValueError, AssertionError) as exc:\n        raise CatalogSnapshotError("Malformed catalog HTML") from exc\n    return parser.result()\n\n\ndef partition_by_catalog(\n    cards: Iterable[Mapping[str, Any]], ids: Iterable[str]\n) -> dict[str, list[Mapping[str, Any]]]:\n    """Keep original rows and order; catalog membership wins over CRM intent."""\n    catalog_ids = set()\n    for number in ids:\n        if not _valid_number(number) or number in catalog_ids:\n            raise CatalogSnapshotError("Invalid or duplicate catalog identifier")\n        catalog_ids.add(number)\n    groups = {"catalog": [], "unpublished": []}\n    seen_ids = set()\n    seen_numbers = set()\n    for card in cards:\n        if not isinstance(card, Mapping):\n            raise CatalogSnapshotError("Invalid CRM car record")\n        cid = card.get("id")\n        number = card.get("auto_number")\n        if type(cid) is not int or cid <= 0 or cid in seen_ids:\n            raise CatalogSnapshotError("Missing, invalid or duplicate CRM car id")\n        if not _valid_number(number) or number in seen_numbers:\n            raise CatalogSnapshotError("Missing, invalid or duplicate CRM car number")\n        seen_ids.add(cid)\n        seen_numbers.add(number)\n        key = "catalog" if number in catalog_ids else "unpublished"\n        groups[key].append(card)\n    if catalog_ids - seen_numbers:\n        raise CatalogSnapshotError("Catalog contains car numbers absent from the CRM snapshot")\n    return groups\n'
FRAGMENT = "# UA-ART-CRM-CATALOG-FOLDERS-001:START\nfrom pathlib import Path as _ua122_Path\nfrom ua_crm_catalog_folders import (\n    parse_catalog as _ua122_parse_catalog,\n    partition_by_catalog as _ua122_partition,\n)\n\n_UA122_CATALOG = _ua122_Path('/home/Carix/video/katalog.html')\n_UA122_LABELS = {'catalog': 'В каталоге', 'unpublished': 'Не опубликованные'}\n_UA122_PAGE_SIZE = 20\n_UA122_BASE_CARD_KB = card_kb\n_UA122_BASE_REGISTER = register\n\n\ndef _ua122_catalog_ids():\n    # An incomplete or concurrently replaced catalog must never empty a folder.\n    before = _UA122_CATALOG.stat()\n    source = _UA122_CATALOG.read_text(encoding='utf-8')\n    after = _UA122_CATALOG.stat()\n    if (before.st_ino, before.st_size, before.st_mtime_ns) != (\n            after.st_ino, after.st_size, after.st_mtime_ns):\n        raise ValueError('Catalog changed while reading')\n    return _ua122_parse_catalog(source)\n\n\nasync def cars_list(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    q = update.callback_query\n    await _v168_ack(q,)\n    staff = db.get_staff(q.from_user.id)\n    if not staff:\n        await q.message.reply_text('Доступ только для сотрудников.')\n        raise ApplicationHandlerStop\n    drop_wait(context)\n    context.user_data.pop('car_last', None)\n    context.user_data.pop('car_voice_active', None)\n    context.user_data.pop('voice_undo', None)\n    try:\n        cards = db.list_cards('cars', limit=-1)\n        groups = _ua122_partition(cards, _ua122_catalog_ids())\n        data = str(q.data or '')\n        if data in ('cards_cars', 'cars_cards'):\n            rows = [[InlineKeyboardButton('%s · %d' % (title, len(groups[key])),\n                     callback_data='ua122_cars:%s:0' % key)]\n                    for key, title in _UA122_LABELS.items()]\n            rows.append([InlineKeyboardButton('← Назад', callback_data='menu')])\n            await q.message.reply_text('Автомобили\\nВыберите папку.',\n                                       reply_markup=InlineKeyboardMarkup(rows))\n            raise ApplicationHandlerStop\n        parts = data.split(':')\n        if (len(parts) != 3 or parts[0] != 'ua122_cars'\n                or parts[1] not in _UA122_LABELS or not parts[2].isascii()\n                or not parts[2].isdigit() or len(parts[2]) > 9):\n            raise ValueError('Invalid folder callback')\n        folder = parts[1]\n        selected = groups[folder]\n        last = max(0, (len(selected) - 1) // _UA122_PAGE_SIZE)\n        page = min(int(parts[2]), last)\n        lines = ['<b>%s · %d</b>' % (_UA122_LABELS[folder], len(selected))]\n        rows = []\n        if not selected:\n            lines.append('В этой папке пока нет автомобилей.')\n        for original in selected[page * _UA122_PAGE_SIZE:(page + 1) * _UA122_PAGE_SIZE]:\n            card = card_of(original['id']) or original\n            miss = S.missing_required(card)\n            state = ('черновик, не хватает %d' % len(miss)) if miss else 'заполнена'\n            stage = S.status_label(card.get('status')) if card.get('status') else 'этап не задан'\n            lines.extend([_ua082_title_html(card), '   %s · %s' % (stage, state)])\n            rows.append([InlineKeyboardButton(_ua082_title_button(card),\n                          callback_data='car_open:%d' % card['id'])])\n        nav = []\n        if page:\n            nav.append(InlineKeyboardButton('←', callback_data='ua122_cars:%s:%d' % (folder, page - 1)))\n        if page < last:\n            nav.append(InlineKeyboardButton('→', callback_data='ua122_cars:%s:%d' % (folder, page + 1)))\n        if nav:\n            lines.append('Страница %d из %d' % (page + 1, last + 1))\n            rows.append(nav)\n        rows.append([InlineKeyboardButton('← Автомобили', callback_data='cards_cars')])\n        await q.message.reply_text('\\n'.join(lines), parse_mode='HTML',\n                                   reply_markup=InlineKeyboardMarkup(rows))\n    except ApplicationHandlerStop:\n        raise\n    except Exception:\n        log.exception('Не удалось прочитать папки автомобилей')\n        await q.message.reply_text(\n            'Не удалось обновить список. Повторите открытие раздела.',\n            reply_markup=InlineKeyboardMarkup([[\n                InlineKeyboardButton('← Автомобили', callback_data='cards_cars')]]))\n    raise ApplicationHandlerStop\n\n\ndef card_kb(card, staff):\n    markup = _UA122_BASE_CARD_KB(card, staff)\n    try:\n        folder = 'catalog' if card.get('auto_number') in _ua122_catalog_ids() else 'unpublished'\n    except Exception:\n        return markup  # Keep the existing return button on read failure.\n    return InlineKeyboardMarkup([\n        [InlineKeyboardButton('← ' + _UA122_LABELS[folder],\n             callback_data='ua122_cars:%s:0' % folder)\n         if getattr(button, 'callback_data', None) in ('cards_cars', 'cars_cards')\n         else button for button in row]\n        for row in markup.inline_keyboard\n    ])\n\n\ndef register(app):\n    _UA122_BASE_REGISTER(app)\n    app.add_handler(CallbackQueryHandler(cars_list,\n        pattern=r'^ua122_cars:(?:catalog|unpublished):[0-9]{1,9}$'), group=-1)\n# UA-ART-CRM-CATALOG-FOLDERS-001:END\n"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def atomic_write(path, data, mode=0o600, create_only=False):
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        if create_only:
            try:
                os.link(temp, path)
            except FileExistsError:
                if path.read_bytes() != data:
                    raise RuntimeError('Core changed; refusing concurrent overwrite')
        else:
            os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def preflight():
    original = SOURCE.read_bytes()
    if sha(original) != EXPECTED:
        raise RuntimeError('Source changed; refusing installation: ' + sha(original))
    if MARKER in original:
        raise RuntimeError('Adapter marker already exists')
    tree = ast.parse(original)
    names = {node.name for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if not {'cars_list', 'card_kb', 'register', 'card_of', 'drop_wait',
            '_ua082_title_html', '_ua082_title_button'} <= names:
        raise RuntimeError('Required current CRM functions missing')
    core = CORE_TEXT.encode('utf-8')
    if CORE.exists() and CORE.read_bytes() != core:
        raise RuntimeError('Core path already contains different code')
    candidate = original + b'\n\n' + FRAGMENT.encode('utf-8')
    compile(core, str(CORE), 'exec')
    compile(candidate, str(SOURCE), 'exec')
    namespace = {'__name__': 'ua122_preflight'}
    exec(compile(core, str(CORE), 'exec'), namespace)
    catalog = ROOT / 'video/katalog.html'
    before = catalog.stat()
    ids = namespace['parse_catalog'](catalog.read_text(encoding='utf-8'))
    after = catalog.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino, after.st_size, after.st_mtime_ns):
        raise RuntimeError('Catalog changed during preflight')
    con = sqlite3.connect('file:' + str(ROOT / 'crm.db') + '?mode=ro', uri=True)
    try:
        con.row_factory = sqlite3.Row
        cards = [dict(row) for row in con.execute(
            'SELECT id, auto_number, published FROM cars ORDER BY id DESC')]
    finally:
        con.close()
    groups = namespace['partition_by_catalog'](cards, ids)
    report = {'source_sha256': sha(original), 'candidate_sha256': sha(candidate),
              'core_sha256': sha(core), 'catalog_count': len(groups['catalog']),
              'unpublished_count': len(groups['unpublished']),
              'unpublished_numbers': [x['auto_number'] for x in groups['unpublished']]}
    return original, candidate, core, report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', metavar='BACKUP_DIRECTORY')
    args = parser.parse_args()
    if args.rollback:
        if args.apply:
            raise RuntimeError('Apply and rollback are mutually exclusive')
        backup = Path(args.rollback).resolve()
        base = (ROOT / 'backups/crm_catalog_folders_001').resolve()
        if backup.parent != base:
            raise RuntimeError('Unexpected backup directory')
        manifest = json.loads((backup / 'manifest.json').read_text())
        original = (backup / 'cars_ui.py').read_bytes()
        if sha(original) != EXPECTED or sha(SOURCE.read_bytes()) != manifest['candidate_sha256']:
            raise RuntimeError('Rollback hash mismatch; refusing concurrent overwrite')
        atomic_write(SOURCE, original, manifest['source_mode'])
        print(json.dumps({'status': 'ROLLED_BACK', 'source_sha256': sha(original)}))
        return
    original, candidate, core, report = preflight()
    if not args.apply:
        print(json.dumps(dict(report, status='PREFLIGHT_OK'), ensure_ascii=False))
        return
    mode = SOURCE.stat().st_mode & 0o777
    backup = ROOT / 'backups/crm_catalog_folders_001' / time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    backup.mkdir(parents=True, exist_ok=False)
    atomic_write(backup / 'cars_ui.py', original)
    atomic_write(backup / 'manifest.json', json.dumps(dict(report, source_mode=mode), indent=2).encode())
    if sha(SOURCE.read_bytes()) != EXPECTED:
        raise RuntimeError('Source changed after preflight; refusing installation')
    atomic_write(CORE, core, 0o644, create_only=True)
    if sha(SOURCE.read_bytes()) != EXPECTED:
        raise RuntimeError('Source changed before replacement; refusing installation')
    atomic_write(SOURCE, candidate, mode)
    if SOURCE.read_bytes() != candidate or CORE.read_bytes() != core:
        raise RuntimeError('Post-write verification failed')
    print(json.dumps(dict(report, status='INSTALLED', backup=str(backup)), ensure_ascii=False))

if __name__ == '__main__':
    main()
