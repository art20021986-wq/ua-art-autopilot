"""Public price view: read-only SQLite, published rows only, no CRM imports."""
import json
import pathlib
import re
import sqlite3
from uaart_public_renderer_v1 import render_market_prices
ROUTE = '/ua-art-public-prices-v1.json'
DB = pathlib.Path('/home/Carix/crm.db')
def snapshot(path=DB):
    connection = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=1)
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.row_factory = sqlite3.Row
        connection.set_authorizer(lambda action,*args: sqlite3.SQLITE_OK if action in {sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ,sqlite3.SQLITE_FUNCTION} else sqlite3.SQLITE_DENY)
        rows = connection.execute('SELECT auto_number,status,price_uah,price_georgia,price_total FROM cars WHERE published=1 ORDER BY id').fetchall()
        result = {}
        for record in rows:
            row = dict(record); code = row['auto_number']
            if not re.fullmatch(r'UA-[0-9]{4}',code or '') or code in result:
                raise ValueError('INVALID_PUBLIC_ID')
            # Strong elements avoid legacy catalog selectors that count all spans.
            def fragment(compact):
                return render_market_prices(row,compact=compact,require_car_id=True).replace('<span ', '<strong ').replace('</span>', '</strong>')
            result[code] = {'compact':fragment(True),'full':fragment(False)}
        return {'version':1,'cars':result}
    finally:
        connection.close()
def wrap(application):
    def public_prices(environ,start_response):
        if environ.get('PATH_INFO') != ROUTE:
            return application(environ,start_response)
        method = environ.get('REQUEST_METHOD','GET')
        headers = [('Content-Type','application/json; charset=utf-8'),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff')]
        if method not in ('GET','HEAD'):
            start_response('405 Method Not Allowed',headers+[('Allow','GET, HEAD')]); return [b'']
        try:
            body = json.dumps(snapshot(),ensure_ascii=False,separators=(',',':')).encode()
            status = '200 OK'
        except (OSError,sqlite3.Error,ValueError,TypeError):
            body = b'{"error":"prices_temporarily_unavailable"}'; status = '503 Service Unavailable'
        start_response(status,headers+[('Content-Length',str(len(body)))])
        return [body if method == 'GET' else b'']
    return public_prices
