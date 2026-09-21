"""Final-write deletion guard. Import has no database or file side effects.

The integrator must keep the existing publication fence through replacement.
Every tombstone state reserves the identity; no temporary bypass is provided.
"""
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path
import hashlib
import json
import re
import sqlite3
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree

ROOT = Path('/home/Carix')
CODE = re.compile(r'UA-[0-9]{4}$')
PAGE = re.compile(r'(UA-[0-9]{4})(?:-diag)?(?:-[0-9a-f]{6,10})?\.html$', re.I)
LITERAL = re.compile(r'''(?<![\w-])(UA-[0-9]{4})(?:-diag)?(?:-[0-9a-f]{6,10})?\.html(?:[?#\s"'<>]|$)''', re.I)

# A separate historical reservation, not a fabricated routine deletion intent.
# These exact bytes record the completed emergency retirement and real audit
# event. The release builder must verify the private evidence before packaging.
HISTORICAL_PLAN_SHA256 = '891dbad7211277f1613655da9cbcb2ea19f80937c375bc2575767858c2aa6442'
HISTORICAL_RECEIPT_SHA256 = 'e12933ef0d154c6a33a76b17b5de90f637e8694aeffda6f7c662a3265d83981d'
HISTORICAL_BACKUP_SHA256 = 'c3af42bf4c401352ee666cbb3610634795bec5b7fc1ef16da2ed817f81837148'
HISTORICAL_RESERVATIONS = (('UA-0002', 8,
    '1b481c41af415946e8721037281b9ccabf09d0f8ddaa5c9739dfbaf8f9746c87'),)


class DeletedPublicationRefused(RuntimeError):
    pass


def vin_key(value):
    return re.sub(r'[\s-]+', '', str(value or '')).upper()


def historical_identity_reserved(code=None, car_id=None, vin=None,
                                 reservations=HISTORICAL_RESERVATIONS):
    key = vin_key(vin)
    digest = hashlib.sha256(key.encode()).hexdigest() if key else None
    return any(code == old_code or car_id == old_id or digest == old_vin_sha
               for old_code, old_id, old_vin_sha in reservations)


def verify_historical_evidence(plan_bytes, receipt_bytes):
    if (hashlib.sha256(plan_bytes).hexdigest() != HISTORICAL_PLAN_SHA256 or
            hashlib.sha256(receipt_bytes).hexdigest() != HISTORICAL_RECEIPT_SHA256):
        raise ValueError('EXACT_HISTORICAL_RETIREMENT_EVIDENCE_REQUIRED')
    plan, receipt = json.loads(plan_bytes), json.loads(receipt_bytes)
    target, result = plan['target'], receipt['installer']
    if (plan['contract'] != 'UA-ART-UA0002-CRITICAL-DELETE-001-v1.0'
            or plan['nonce'] != 'ua0002-20260921-0453'
            or target['auto_number'] != 'UA-0002' or target['id'] != 8
            or hashlib.sha256(vin_key(target['vin']).encode()).hexdigest() != HISTORICAL_RESERVATIONS[0][2]
            or receipt['status'] != 'PASS' or not receipt['safe_to_stop']
            or receipt['plan_sha256'] != HISTORICAL_PLAN_SHA256
            or result['status'] != 'PASS' or not result['target_absent']
            or not result['target_retired_local']
            or result['backup_manifest_sha256'] != HISTORICAL_BACKUP_SHA256
            or result['database_structure']['card_delete']['matches'] != 1
            or result['database_structure']['card_delete']['observed'] is not True):
        raise ValueError('HISTORICAL_RETIREMENT_PROOF_INVALID')
    return {'code': 'UA-0002', 'car_id': 8,
            'vin_sha256': HISTORICAL_RESERVATIONS[0][2],
            'plan_sha256': HISTORICAL_PLAN_SHA256,
            'receipt_sha256': HISTORICAL_RECEIPT_SHA256,
            'backup_manifest_sha256': HISTORICAL_BACKUP_SHA256}


def sitemap_codes(payload):
    try:
        tree = ElementTree.fromstring(payload)
    except (ElementTree.ParseError, TypeError, ValueError) as exc:
        raise DeletedPublicationRefused('VALID_SITEMAP_REQUIRED') from exc
    if tree.tag.rsplit('}', 1)[-1] != 'urlset':
        raise DeletedPublicationRefused('SITEMAP_URLSET_REQUIRED')
    codes = set()
    for loc in tree.iter():
        if loc.tag.rsplit('}', 1)[-1] != 'loc':
            continue
        name = unquote(urlsplit((loc.text or '').strip()).path).rsplit('/', 1)[-1]
        match = PAGE.fullmatch(name)
        if match:
            codes.add(match[1].upper())
    return codes


def advertised_codes(payload):
    if isinstance(payload, bytes):
        payload = payload.decode('utf-8')
    if not isinstance(payload, str):
        raise DeletedPublicationRefused('PUBLIC_HTML_REQUIRED')
    result = {m[1].upper() for m in LITERAL.finditer(payload)}

    class Parser(HTMLParser):
        def handle_starttag(self, tag, pairs):
            attrs = dict(pairs)
            for key in ('data-ua-card', 'data-ua', 'data-car-code'):
                value = str(attrs.get(key) or '').strip().upper()
                if CODE.fullmatch(value):
                    result.add(value)
            for key in ('href', 'action'):
                name = unquote(urlsplit(attrs.get(key) or '').path).rsplit('/', 1)[-1]
                match = PAGE.fullmatch(name)
                if match:
                    result.add(match[1].upper())

    parser = Parser()
    parser.feed(payload)
    parser.close()
    return result


class PublicDeletionGuard:
    def __init__(self, root, db_path, fence, require_fence,
                 historical_reservations=HISTORICAL_RESERVATIONS):
        self.root, self.db_path = Path(root), Path(db_path)
        if not self.root.is_absolute() or not self.db_path.is_absolute():
            raise ValueError('ABSOLUTE_ROOT_AND_DATABASE_REQUIRED')
        self.fence, self.require_fence = fence, require_fence
        self.historical_reservations = historical_reservations

    def public_path(self, value):
        path = Path(value)
        if not path.is_absolute():
            raise DeletedPublicationRefused('ABSOLUTE_DESTINATION_REQUIRED')
        # Only approved public trees; backup/log/temp paths retain their owners.
        if not any(path.is_relative_to(self.root / folder) for folder in ('video', 'site')):
            return None
        if self.root.resolve(strict=True) != self.root or path.resolve(strict=False) != path:
            raise DeletedPublicationRefused('CANONICAL_PUBLIC_DESTINATION_REQUIRED')
        if path.parent.resolve(strict=True) != path.parent or path.is_symlink():
            raise DeletedPublicationRefused('CANONICAL_PUBLIC_DESTINATION_REQUIRED')
        if path.suffix.lower() != '.html' and path.name != 'sitemap.xml':
            return None
        if path.name.upper().startswith('UA-') and not PAGE.fullmatch(path.name):
            raise DeletedPublicationRefused('UNKNOWN_CAR_ALIAS')
        return path

    @contextmanager
    def connection(self):
        self.require_fence()
        if self.db_path.resolve(strict=True) != self.db_path:
            raise DeletedPublicationRefused('CANONICAL_DATABASE_REQUIRED')
        conn = sqlite3.connect(self.db_path.as_uri() + '?mode=ro', uri=True, timeout=2)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN')
            columns = {row[1] for row in conn.execute('PRAGMA table_info(ua_delete_intents)')}
            if not {'car_id', 'car_code', 'vin'} <= columns:
                raise DeletedPublicationRefused('DELETION_SCHEMA_REQUIRED')
            yield conn
        finally:
            conn.close()

    def _active(self, conn, code, car_id=None, vin=None, require_published=True):
        if not CODE.fullmatch(str(code)):
            raise DeletedPublicationRefused('EXACT_CAR_CODE_REQUIRED')
        if historical_identity_reserved(code, car_id, vin, self.historical_reservations):
            raise DeletedPublicationRefused('HISTORICAL_DELETION_IDENTITY_RESERVED')
        rows = conn.execute('SELECT id,auto_number,vin,published FROM cars WHERE auto_number=?', (code,)).fetchall()
        if len(rows) != 1 or (require_published and rows[0]['published'] != 1):
            raise DeletedPublicationRefused('CURRENT_PUBLISHED_CAR_REQUIRED')
        row = rows[0]
        if historical_identity_reserved(code, row['id'], row['vin'], self.historical_reservations):
            raise DeletedPublicationRefused('HISTORICAL_DELETION_IDENTITY_RESERVED')
        if car_id is not None and row['id'] != car_id:
            raise DeletedPublicationRefused('CAR_IDENTITY_CHANGED')
        if vin is not None and vin_key(row['vin']) != vin_key(vin):
            raise DeletedPublicationRefused('CAR_IDENTITY_CHANGED')
        # Iterate because older candidate rows may retain VIN separators.
        for intent in conn.execute('SELECT car_id,car_code,vin FROM ua_delete_intents'):
            if (intent['car_id'] == row['id'] or intent['car_code'] == code or
                    (vin_key(intent['vin']) and vin_key(intent['vin']) == vin_key(row['vin']))):
                raise DeletedPublicationRefused('DELETION_IDENTITY_RESERVED')
        return dict(row)

    def require_active(self, code, car_id=None, vin=None):
        with self.connection() as conn:
            return self._active(conn, code, car_id, vin)

    def require_current(self, code, car_id=None, vin=None):
        with self.connection() as conn:
            return self._active(conn, code, car_id, vin, require_published=False)

    def check_locked(self, path, payload):
        self.require_fence()
        path = self.public_path(path)
        if path is None:
            return
        codes = sitemap_codes(payload) if path.name == 'sitemap.xml' else advertised_codes(payload)
        match = PAGE.fullmatch(path.name)
        if match:
            codes.add(match[1].upper())
        with self.connection() as conn:
            retired = {row[0] for row in conn.execute('SELECT car_code FROM ua_delete_intents')}
            retired.update(item[0] for item in self.historical_reservations)
            if codes & retired:
                raise DeletedPublicationRefused('DELETED_CAR_PUBLIC_WRITE_REFUSED')
            for code in sorted(codes):
                self._active(conn, code, require_published=False)

    @contextmanager
    def write(self, path, payload):
        with self.fence():
            self.check_locked(path, payload)
            yield


def production_guard():
    from publication_fence import publication_fence, require_publication_fence
    return PublicDeletionGuard(ROOT, ROOT / 'crm.db',
                               lambda: publication_fence(timeout=90.0), require_publication_fence)


@contextmanager
def guarded_write(path, payload):
    with production_guard().write(path, payload):
        yield


def check_locked(path, payload):
    production_guard().check_locked(path, payload)


def require_active(code, car_id=None, vin=None):
    return production_guard().require_active(code, car_id=car_id, vin=vin)


def require_current(code, car_id=None, vin=None):
    return production_guard().require_current(code, car_id=car_id, vin=vin)
