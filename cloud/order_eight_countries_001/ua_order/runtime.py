"""Explicit runtime composition. No migration or secret creation at import time."""
from dataclasses import dataclass
import json
import os
from pathlib import Path

from .auth import WebSessions
from .catalog import Catalog
from .rate_limit import RateLimit
from .repository import APPLICATION_ID, Repository
from .service import OrderService

DEFAULT_SETTINGS = Path('/home/Carix/order_requests/settings.json')
NETWORK_FILESYSTEMS = {'nfs', 'nfs4', 'cifs', 'smbfs', 'ceph', 'glusterfs', '9p'}


def storage_filesystem(path, mountinfo):
    """Find the most specific Linux mount for a resolved path."""
    path = Path(path).resolve()
    matches = []
    for line in mountinfo.splitlines():
        before, sep, after = line.partition(' - ')
        if not sep:
            continue
        fields = before.split()
        if len(fields) < 5 or not after.split():
            continue
        mount = Path(fields[4].replace('\\040', ' ').replace('\\134', '\\'))
        if path == mount or mount in path.parents:
            matches.append((len(mount.parts), after.split()[0]))
    if not matches:
        raise ValueError('Cannot verify the order database filesystem')
    return max(matches)[1]


def require_local_storage(path):
    filesystem = storage_filesystem(path, Path('/proc/self/mountinfo').read_text())
    if filesystem in NETWORK_FILESYSTEMS or filesystem.startswith('fuse'):
        raise ValueError('SQLite WAL cannot be shared across hosts on a network filesystem')


@dataclass
class Runtime:
    service: OrderService
    strings: dict
    consent_text: dict
    media_root: Path
    sessions: WebSessions
    origin: str
    bot_token: str
    web_users: RateLimit
    web_addresses: RateLimit
    bot_users: RateLimit

    def allow_update(self, update):
        return bool(update.effective_user and self.bot_users.allow(update.effective_user.id))

    def allow_request(self, env, principal):
        # REMOTE_ADDR is server-supplied. Never trust a client Forwarded header.
        address = env.get('REMOTE_ADDR')
        return bool(address and self.web_addresses.allow(address)
                    and self.web_users.allow(principal.owner))


def load(settings_path=None):
    path = Path(settings_path or os.environ.get('UA_ORDER_SETTINGS') or DEFAULT_SETTINGS).resolve()
    if not path.is_file():
        return None
    settings = json.loads(path.read_text(encoding='utf-8'))
    if settings.get('enabled') is not True:
        return None
    if settings.get('storage') != 'local_sqlite':
        raise ValueError('Configure an audited storage backend before enabling orders')
    consent = settings.get('consent_text')
    if (not isinstance(consent, dict) or set(consent) != {'uk', 'ru', 'ka'}
            or not all(isinstance(v, str) and v.strip() for v in consent.values())):
        raise ValueError('The approved company consent is required in three languages')
    version = settings.get('consent_version')
    if not isinstance(version, str) or not version.strip():
        raise ValueError('The approved consent version is required')
    origin = settings.get('origin', '')
    if not origin.startswith('https://') or origin.endswith('/'):
        raise ValueError('An exact HTTPS origin is required')
    database = path.parent / 'order_requests.db'
    require_local_storage(database)
    repository = Repository(database)
    # Explicit setup must precede startup; this cannot create a new empty DB.
    with repository.connection() as db:
        if (db.execute('PRAGMA application_id').fetchone()[0] != APPLICATION_ID
                or db.execute('PRAGMA user_version').fetchone()[0] != 1):
            raise ValueError('Initialize the isolated order database before enabling intake')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'order_requests', 'order_events', 'order_outbox', 'order_drafts',
                'order_notification_receipts'} <= tables:
            raise ValueError('The order database setup is incomplete')
    catalog = Catalog(settings['catalog_path'])
    media_root = Path(settings['media_root']).resolve()
    if not media_root.is_dir():
        raise ValueError('Install order media before enabling intake')
    secret = (path.parent / 'session.key').read_bytes()
    # Match lead_bot.read_token without importing its side-effectful module.
    token = os.environ.get('BOT_TOKEN', '').strip()
    if not token:
        token = Path('/home/Carix/bot_token.txt').read_text().strip()
    if not token:
        raise ValueError('The existing customer bot token is required')
    return Runtime(
        OrderService(catalog, repository, version),
        json.loads(Path(settings['strings_path']).read_text()), consent, media_root,
        WebSessions(secret), origin, token,
        RateLimit(10), RateLimit(60), RateLimit(60),
    )
