"""Non-destructive v2 integration probe, pinned to Carix$orders_test only.

Uses the existing server driver/config file; no production DB or Telegram API.
Deletes only this run's UUID/owner rows, including on failure. No table clearing.
"""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests'))
from ua_order.catalog import Catalog
from ua_order.contract import digest
from ua_order.mysql_repository import MySQLRepository
from ua_order.service import OrderService,Principal
from ua_order import bot_flow,crm
from test_preferences import sample


def run():
    repository=MySQLRepository(host='Carix.mysql.pythonanywhere-services.com',user='Carix',database='Carix$orders_test',defaults_file='/home/Carix/.my.cnf')
    repository.check_ready()
    catalog=Catalog(ROOT.parent/'ua_order_ge_8country_guard_016/country_models.json')
    service=OrderService(catalog,repository,'test-consent-v1')
    owner='web:preferences-test-'+str(uuid4());actor=Principal(owner,'site')
    data=sample(catalog);data['consent']['version']='test-consent-v1';data['comment']='🚗'*3000
    data['make']='toyota';data['models']=['Camry'];request_id=data['request_id']
    clean=service.normalize(data,actor)
    report={'test_database':'Carix$orders_test','production_write':False,'real_messages_sent':False}
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts=list(pool.map(lambda _:service.submit(copy.deepcopy(data),actor),range(8)))
        assert len({r['number'] for r in receipts})==1
        stored=repository.notification_data(request_id)
        assert stored['data']==clean
        assert repository.receipt_for_owner(request_id,owner)==receipts[0]
        def counts(cursor):
            cursor.execute('SELECT DATABASE() AS name');assert cursor.fetchone()['name']=='Carix$orders_test'
            output={}
            for table in ('order_requests','order_outbox'):
                cursor.execute('SELECT COUNT(*) AS count FROM '+table+' WHERE request_id=%s',(request_id,));output[table]=cursor.fetchone()['count']
            return output
        assert repository._run(counts)=={'order_requests':1,'order_outbox':1}
        token=service.handoff(data,actor);redeemed=repository.redeem_draft(token,'telegram:123')
        assert redeemed==clean
        strings=json.loads((ROOT/'strings.json').read_text());consent={lang:strings[lang]['consent'] for lang in strings}
        flow=bot_flow.create(catalog,data=redeemed);flow['step']='review'
        view=bot_flow.view(flow,catalog,strings,consent);assert ''.join(view['parts'])==view['text'];assert len(view['parts'])>1
        detail=crm.detail_view(stored,catalog);assert 'Camry' in detail['text'];assert len(detail['parts'])>1
        report.update(result='PASS',checks=['concurrent v2 submit: one row and outbox','all final preferences survive MySQL utf8mb4 roundtrip','3000 supplementary Unicode characters preserved','owned receipt after commit','full website-to-Telegram draft and review','complete split owner-inbox detail'])
    finally:
        def cleanup(cursor):
            cursor.execute('SELECT DATABASE() AS name')
            if cursor.fetchone()['name']!='Carix$orders_test':raise RuntimeError('Refusing cleanup outside test database')
            cursor.execute('SELECT owner FROM order_requests WHERE request_id=%s',(request_id,));row=cursor.fetchone()
            if row and row['owner']!=owner:raise RuntimeError('Refusing cleanup of another run')
            for table in ('order_notification_receipts','order_outbox','order_events'):
                cursor.execute('DELETE FROM '+table+' WHERE request_id=%s',(request_id,))
            cursor.execute('DELETE FROM order_requests WHERE request_id=%s AND owner=%s',(request_id,owner))
            cursor.execute('DELETE FROM order_drafts WHERE owner=%s',(owner,))
        repository._run(cleanup,write=True)
    return report


if __name__=='__main__':print(json.dumps(run(),ensure_ascii=False,indent=2))
