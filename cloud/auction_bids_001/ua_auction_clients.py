"""Auction clients (JPAUTO-KOREA-001, owner 2026-11-10): people with a contract who may bid online.

Created by a manager in the CRM bot after the contract; the login is the phone number, the password is generated
here and shown once. Only a salted scrypt hash of the password is stored (hashlib, standard library).
Bid limit: every 2 000 $ of deposit allows bids up to 15 000 $ (owner 2026-11-10).
One responsibility: the client records. No Telegram, no web code here.
"""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
from pathlib import Path
import re
import secrets
import sqlite3

DB = Path('/home/Carix/auction_clients/clients.db')
ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O, 1/l/I look-alikes
PASSWORD_LENGTH = 8
DEPOSIT_STEP, LIMIT_STEP = 2000, 15000
_SCRYPT = {'n': 2 ** 14, 'r': 8, 'p': 1, 'dklen': 32}
_PHONE = re.compile(r'\+?[0-9]{10,15}')
SCHEMA = '''CREATE TABLE IF NOT EXISTS clients (
    phone TEXT PRIMARY KEY, surname TEXT NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL, city TEXT NOT NULL,
    deposit_usd INTEGER NOT NULL, salt BLOB NOT NULL, password_hash BLOB NOT NULL, blocked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, created_by INTEGER NOT NULL, updated_at TEXT NOT NULL)'''
PUBLIC = ('phone', 'surname', 'name', 'email', 'city', 'deposit_usd', 'blocked', 'created_at')


class ClientError(ValueError):
    """A manager's input the bot should ask for again (the message is the field name)."""


def phone(value):
    """'+38 (099) 111-22-33' -> '+380991112233'."""
    digits = re.sub(r'[\s()\-]', '', str(value))
    if not _PHONE.fullmatch(digits):
        raise ClientError('phone')
    return digits if digits.startswith('+') else '+' + digits


def limit_usd(deposit_usd):
    return deposit_usd // DEPOSIT_STEP * LIMIT_STEP


def new_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(PASSWORD_LENGTH))


def _hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, **_SCRYPT)


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _connect(db=None):
    db = db or DB
    db.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    connection = sqlite3.connect(db, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(SCHEMA)
    return connection


def _text(value, field, maximum=80):
    value = ' '.join(str(value).split())
    if not 1 <= len(value) <= maximum:
        raise ClientError(field)
    return value


def deposit(value):
    """Deposit in whole dollars, at least one step (2 000 $)."""
    try:
        amount = int(str(value).replace(' ', '').replace('$', ''))
    except ValueError:
        raise ClientError('deposit') from None
    if amount < DEPOSIT_STEP or amount > 10 ** 7:
        raise ClientError('deposit')
    return amount


def create(surname, name, phone_number, email, city, deposit_usd, manager_id, db=None):
    """New client -> (client dict, password shown once). A phone already registered is refused."""
    record = {'phone': phone(phone_number), 'surname': _text(surname, 'surname'), 'name': _text(name, 'name'),
              'email': _text(email, 'email', 120), 'city': _text(city, 'city'), 'deposit_usd': deposit(deposit_usd)}
    if '@' not in record['email']:
        raise ClientError('email')
    password, salt = new_password(), secrets.token_bytes(16)
    now = _now()
    with closing(_connect(db)) as connection, connection:
        try:
            connection.execute(
                'INSERT INTO clients (phone, surname, name, email, city, deposit_usd, salt, password_hash, blocked, '
                'created_at, created_by, updated_at) VALUES (?,?,?,?,?,?,?,?,0,?,?,?)',
                (record['phone'], record['surname'], record['name'], record['email'], record['city'],
                 record['deposit_usd'], salt, _hash(password, salt), now, int(manager_id), now))
        except sqlite3.IntegrityError:
            raise ClientError('phone_exists') from None
    return get(record['phone'], db), password


def get(phone_number, db=None):
    with closing(_connect(db)) as connection:
        row = connection.execute('SELECT * FROM clients WHERE phone = ?', (phone(phone_number),)).fetchone()
    return None if row is None else {key: row[key] for key in PUBLIC} | {'limit_usd': limit_usd(row['deposit_usd'])}


def all_clients(db=None):
    with closing(_connect(db)) as connection:
        rows = connection.execute('SELECT * FROM clients ORDER BY created_at DESC').fetchall()
    return [{key: row[key] for key in PUBLIC} | {'limit_usd': limit_usd(row['deposit_usd'])} for row in rows]


def _update(phone_number, db, **fields):
    fields['updated_at'] = _now()
    with closing(_connect(db)) as connection, connection:
        changed = connection.execute(
            'UPDATE clients SET %s WHERE phone = ?' % ', '.join('%s = ?' % key for key in fields),
            (*fields.values(), phone(phone_number))).rowcount
    if changed != 1:
        raise ClientError('not_found')
    return get(phone_number, db)


def reset_password(phone_number, db=None):
    """New password (shown once); the old one stops working at once."""
    password, salt = new_password(), secrets.token_bytes(16)
    _update(phone_number, db, salt=salt, password_hash=_hash(password, salt))
    return password


def set_blocked(phone_number, blocked, db=None):
    return _update(phone_number, db, blocked=1 if blocked else 0)


def set_deposit(phone_number, deposit_usd, db=None):
    return _update(phone_number, db, deposit_usd=deposit(deposit_usd))


def verify(phone_number, password, db=None):
    """The client for a correct login of an active client, else None (same work either way)."""
    try:
        key = phone(phone_number)
    except ClientError:
        key = ''
    with closing(_connect(db)) as connection:
        row = connection.execute('SELECT * FROM clients WHERE phone = ?', (key,)).fetchone()
    salt = row['salt'] if row else b'\0' * 16
    ok = hmac.compare_digest(_hash(str(password), salt), row['password_hash'] if row else b'\0' * 32)
    if not row or not ok or row['blocked']:
        return None
    return {key: row[key] for key in PUBLIC} | {'limit_usd': limit_usd(row['deposit_usd'])}


def session_key(phone_number, db=None):
    """A short fingerprint of the current password of an active client, or None.

    Signed into the site's login cookie: a new password or a block ends every open session at once.
    """
    try:
        key = phone(phone_number)
    except ClientError:
        return None
    with closing(_connect(db)) as connection:
        row = connection.execute('SELECT password_hash, blocked FROM clients WHERE phone = ?', (key,)).fetchone()
    if row is None or row['blocked']:
        return None
    return hashlib.sha256(row['password_hash']).hexdigest()[:16]
