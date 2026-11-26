"""Country a CRM car was bought in (JAPAN-STOCK-001): «korea» or «japan».

Kept in its own table car_country of crm.db, so the cars rows and their schema stay as they are.
A car without a row is a Korean car (every car before JAPAN-STOCK-001). The table is created on the
first save; until then every reader gets «korea». Connections and the edit journal are the CRM's own (db.py).
"""
from contextlib import closing
import sqlite3

import db

KOREA = 'korea'
JAPAN = 'japan'
COUNTRIES = (KOREA, JAPAN)
_TABLE = ('CREATE TABLE IF NOT EXISTS car_country ('
          'car_id INTEGER PRIMARY KEY, '
          "country TEXT NOT NULL CHECK (country IN ('korea', 'japan')), "
          'updated_at TEXT NOT NULL)')


def _no_table(error):
    return isinstance(error, sqlite3.OperationalError) and 'no such table' in str(error)


def _read(query, args=()):
    try:
        with closing(db.connect()) as connection:
            return connection.execute(query, args).fetchall()
    except sqlite3.OperationalError as error:
        if _no_table(error):
            return []
        raise


def country_of(car_id):
    """The car's country; «korea» when nothing was saved for it."""
    rows = _read('SELECT country FROM car_country WHERE car_id = ?', (int(car_id),))
    return rows[0][0] if rows and rows[0][0] in COUNTRIES else KOREA


def japan_ids():
    """Ids of the cars saved as Japanese (all others are Korean)."""
    return frozenset(row[0] for row in _read("SELECT car_id FROM car_country WHERE country = 'japan'"))


def set_country(car_id, country, actor_id):
    """Save the car's country and journal a change like any card field; returns True when it changed."""
    if country not in COUNTRIES:
        raise ValueError('COUNTRY:%r' % (country,))
    car_id = int(car_id)
    if country == KOREA and country_of(car_id) == KOREA:
        return False  # the default: nothing to save
    with closing(db.connect()) as connection, connection:
        connection.execute(_TABLE)
        row = connection.execute('SELECT country FROM car_country WHERE car_id = ?', (car_id,)).fetchone()
        before = row[0] if row else KOREA
        if before == country:
            return False
        connection.execute('INSERT INTO car_country (car_id, country, updated_at) VALUES (?, ?, ?) '
                           'ON CONFLICT(car_id) DO UPDATE SET country = excluded.country, '
                           'updated_at = excluded.updated_at', (car_id, country, db.now()))
    db.log_action(actor_id, 'card_edit', 'cars', car_id, 'country', before, country)
    return True
