"""Read-only verification of current spec generations and public projections."""
import json
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path('/home/Carix')
sys.path.insert(0, str(ROOT))
import ua_spec84_runtime as runtime
import spec_model_profiles as models
import ua_spec_permanent as markup


def main():
    result = {'policy': models.VERSION, 'cards': []}
    with sqlite3.connect('file:' + str(ROOT / 'vin_specs_issue84_queue.db') + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT value_json FROM spec84_runtime_state WHERE key='heartbeat'").fetchone()
        result['heartbeat'] = json.loads(row[0]) if row else None
        for card in runtime._cards():
            if not card.get('published'):
                continue
            uid = card['car_uid']
            cycle = db.execute('SELECT c.* FROM spec84_cycles c JOIN spec84_generations g ON g.uid=c.uid AND g.generation=c.generation WHERE c.uid=?', (uid,)).fetchone()
            sync = db.execute('SELECT state,generation FROM spec84_sync WHERE uid=?', (uid,)).fetchone()
            item = {'uid': uid, 'profile': (models.resolve(card) or {}).get('id'),
                    'cycle': dict(cycle) if cycle else None, 'sync': dict(sync) if sync else None, 'pages': {}}
            if item['cycle']:
                item['cycle'].pop('vin', None)
                item['slots'] = [dict(r) for r in db.execute('SELECT slot,state,result_json FROM spec84_slots WHERE cycle_id=? ORDER BY slot', (cycle['id'],))]
            for folder in ('video', 'site'):
                path = ROOT / folder / (uid + '.html')
                text = path.read_text() if path.is_file() else ''
                spans, _ = markup.owned_spans(text)
                blocks = [text[a:b] for a, b, kind in spans if kind == 'block']
                fields = sum(len(markup.validate_block(block)) for block in blocks)
                forbidden = bool(re.search(r'закуп|себесто|собіварт|purchase|acquisition|buy_price', '\n'.join(blocks), re.I))
                item['pages'][folder] = {'blocks': len(blocks), 'fields': fields, 'purchase_fields': forbidden}
            result['cards'].append(item)
        result['sources'] = [dict(r) for r in db.execute('SELECT s.source_id,s.outcome_json FROM spec84_sources s JOIN spec84_cycles c ON c.id=s.cycle_id JOIN spec84_generations g ON g.uid=c.uid AND g.generation=c.generation WHERE s.slot=0')]
    target = ROOT / 'spec_audit_20260928' / 'after.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    compact = {k: v for k, v in result.items() if k not in ('cards', 'sources')}
    compact['cards'] = [{'uid': c['uid'], 'profile': c['profile'], 'sync': c['sync'],
                        'pages': c['pages'], 'slots': [(s['slot'], s['state']) for s in c.get('slots', [])]} for c in result['cards']]
    print(json.dumps(compact, ensure_ascii=False))


if __name__ == '__main__':
    main()
