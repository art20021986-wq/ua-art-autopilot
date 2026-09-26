"""Exact counter patch regressions with real saved HTML and Node client parity."""
import ast
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import types
import unittest

import patch_site_counters as patcher


class TreeParser(HTMLParser):
    """Generic DOM fixture transport; selectors execute in Node, not Python."""
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = {'tag':'document','attrs':{},'children':[]}
        self.stack = [self.root]
        self.feed(source)
        self.close()
    def handle_starttag(self, tag, pairs):
        node = {'tag':tag,'attrs':dict(pairs),'children':[]}
        self.stack[-1]['children'].append(node)
        if tag not in self.VOID:
            self.stack.append(node)
    def handle_endtag(self, tag):
        for index in range(len(self.stack)-1, 0, -1):
            if self.stack[index]['tag'] == tag:
                del self.stack[index:]
                break
    def handle_startendtag(self, tag, pairs):
        self.handle_starttag(tag, pairs)
        if tag not in self.VOID:
            self.handle_endtag(tag)


NODE_PROBE = r'''
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0,'utf8'));
class Node {
  constructor(raw,parent=null) {this.tag=raw.tag;this.attrs=raw.attrs;this.parent=parent;
    this.children=raw.children.map(child=>new Node(child,this));}
  getAttribute(key) {return this.hasAttribute(key) ? this.attrs[key] : null;}
  hasAttribute(key) {return Object.prototype.hasOwnProperty.call(this.attrs,key);}
  matches(selector) {
    const found = selector.match(/^([a-z]+)?(?:\.([a-z-]+))?(?:\[([a-z-]+)\])?$/);
    if(!found) throw Error('Unsupported test selector:'+selector);
    return (!found[1] || this.tag===found[1]) && (!found[2] ||
      (this.getAttribute('class')||'').split(/\s+/).includes(found[2])) &&
      (!found[3] || this.hasAttribute(found[3]));
  }
  querySelectorAll(selector) {const choices=selector.split(',');const result=[];
    function visit(node) {for(const child of node.children) {
      if(choices.some(choice=>child.matches(choice))) result.push(child);visit(child);}}
    visit(this);return result;}
  querySelector(selector) {return this.querySelectorAll(selector)[0]||null;}
  closest(selector) {for(let node=this;node;node=node.parent) if(node.matches(selector)) return node;return null;}
}
const exported={exports:{}};
new Function('module',input.script)(exported);
const results=input.trees.map(tree=>{try {return {ok:true,counts:exported.exports.snapshot(new Node(tree))};}
  catch(error) {return {ok:false,error:error.message};}});
process.stdout.write(JSON.stringify(results));
'''


def document(cards):
    return '<html><body><div class="catalog-grid">'+cards+'</div></body></html>'


def card(code='UA-0001', stage='korea', contents='', extra=''):
    return '<article class="catalog-card" data-ua-card="%s" data-category="%s" %s>%s</article>' % (code,stage,extra,contents)


class SiteCounterPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_path=Path(os.environ['UA114_COUNTER_SOURCE'])
        cls.original=cls.source_path.read_text()
        cls.candidate=patcher.patch_source(cls.original)
        cls.counter=types.ModuleType('isolated_counter_candidate')
        exec(compile(cls.candidate,'<isolated-counter-candidate>','exec'),cls.counter.__dict__)

    def server_result(self, source):
        try:
            records,counts=self.counter.catalog_snapshot(source)
            return {'ok':True,'counts':counts}
        except self.counter.HomeCounterError as exc:
            return {'ok':False,'error':str(exc)}

    def both(self, sources):
        payload={'script':self.counter.CLIENT_SCRIPT,'trees':[TreeParser(value).root for value in sources]}
        result=subprocess.run([os.environ.get('CODEX_PRIMARY_RUNTIME_NODE','node'),'-e',NODE_PROBE],
            input=json.dumps(payload),text=True,capture_output=True,check=True,timeout=15)
        client=json.loads(result.stdout)
        server=[self.server_result(value) for value in sources]
        for left,right in zip(server,client):
            self.assertEqual(left['ok'],right['ok'])
            if left['ok']:
                self.assertEqual(left['counts'],right['counts'])
        return server,client

    def test_exact_source_pin_refuses_drift_and_double_apply(self):
        for value in (self.original+'\n',self.candidate,'untrusted',None):
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA256_MISMATCH'):
                patcher.patch_source(value)

    def test_unrelated_server_methods_and_client_program_unchanged(self):
        oldtree=ast.parse(self.original)
        newtree=ast.parse(self.candidate)
        for tree in (oldtree,newtree):
            for node in tree.body:
                if isinstance(node,ast.Assign) and any(isinstance(n,ast.Name) and n.id=='CLIENT_SCRIPT' for n in node.targets):
                    node.value=ast.Constant(value='client compared separately')
                if isinstance(node,ast.ClassDef) and node.name=='CatalogParser':
                    node.body=[method for method in node.body if not isinstance(method,ast.FunctionDef) or method.name!='handle_starttag']
        self.assertTrue(ast.dump(oldtree)==ast.dump(newtree))
        before=next(n.value.value for n in ast.parse(self.original).body if isinstance(n,ast.Assign)
                    and any(isinstance(t,ast.Name) and t.id=='CLIENT_SCRIPT' for t in n.targets))
        after=self.counter.CLIENT_SCRIPT.replace(patcher.CLIENT_AFTER,patcher.CLIENT_BEFORE).replace(patcher.SELECTOR_AFTER,patcher.SELECTOR_BEFORE)
        self.assertTrue(before==after)

    def test_translation_captions_and_legacy_descendant_match_client(self):
        sources=[document(card(contents='<span data-ua="Україна" data-ru="Украина">Україна</span>'
            '<span data-ua="Ціна уточнюється" data-category="korea">Ціна уточнюється</span>')),
            document('<article class="catalog-card" data-category="sea"><b data-ua=" ua-0017 "></b>'
                '<span data-ua="Доставка до Києва"></span></article>')]
        server,_=self.both(sources)
        self.assertEqual([item['counts']['all'] for item in server],[1,1])
        self.assertEqual(server[1]['counts']['sea'],1)

    def test_explicit_malformed_marker_never_uses_valid_href_fallback(self):
        sources=[document(card(code=value,contents='<a href="UA-0001.html">Open</a>'))
                 for value in ('','UA-1','UA-ABCD','caption','UA-0001 extra')]
        server,client=self.both(sources)
        self.assertTrue(all(not item['ok'] for item in server+client))
        self.assertTrue(all(item['error']=='INVALID_ID' for item in server))

    def test_conflicting_valid_ids_and_duplicate_stages_remain_rejected(self):
        sources=[document(card(extra='data-ua="UA-0002"')),
            document(card()+card(stage='sea')),
            document(card(contents='<span data-ua-card="UA-0002"></span>')),
            document(card(contents='<span data-stage="georgia"></span>'))]
        server,client=self.both(sources)
        self.assertTrue(all(not item['ok'] for item in server+client))

    def test_legacy_href_fallback_and_explicit_id_precedence_are_preserved(self):
        sources=[document('<article class="catalog-card" data-category="kyiv" data-ua="Україна">'
            '<a href="/video/UA-0003.html?language=ua">Open</a></article>'),
            document(card(contents='<a href="/video/UA-0099.html">Existing fallback precedence</a>')),
            document('<article class="catalog-card" data-ua="UA-1"></article>')]
        server,_=self.both(sources)
        self.assertEqual(server[0]['counts']['kiev'],1)
        self.assertEqual(server[1]['counts']['all'],1)
        self.assertFalse(server[2]['ok'])

    def test_zero_new_car_and_same_stage_duplicates_are_dynamic(self):
        sources=[document(''),document(card()),document(card()+card(code='UA-0002',stage='georgia')),
                 document(card()+card())]
        server,_=self.both(sources)
        self.assertEqual([item['counts']['all'] for item in server],[0,1,2,1])
        self.assertEqual(server[2]['counts']['georgia'],1)

    def test_count_updates_preserve_unrelated_layout_and_language_attributes(self):
        source=document(card(contents='<span data-ua="Україна" data-ru="Украина">Україна</span>'))
        filters=''.join('<button data-f="%s">old</button>'%key for key in ('all','kiev','georgia','sea','korea'))
        source=source.replace('</body>',filters+'<script id="unrelated">window.keep=1;</script></body>')
        _,counts=self.counter.catalog_snapshot(source)
        changed=self.counter.patch_catalog(source,counts)
        self.assertIn(card(contents='<span data-ua="Україна" data-ru="Украина">Україна</span>'),changed)
        self.assertIn('<script id="unrelated">window.keep=1;</script>',changed)
        self.assertEqual(self.counter.patch_catalog(changed,counts),changed)
        self.assertEqual(self.counter.catalog_snapshot(changed)[1],counts)

    def test_actual_retained_dual_price_catalog_counts_without_editing_input(self):
        path=Path(os.environ['UA114_COUNTER_REAL_CATALOG'])
        before=path.read_bytes()
        records,counts=self.counter.catalog_snapshot(before.decode())
        self.assertEqual(len(records),18)
        self.assertEqual(counts['all'],18)
        self.assertEqual(sum(counts[stage] for stage in self.counter.STAGES),18)
        self.assertEqual(hashlib.sha256(path.read_bytes()).digest(),hashlib.sha256(before).digest())

    def test_inline_script_migration_preserves_all_other_html_and_is_idempotent(self):
        before_script=patcher._client_literal(self.original)
        html='<html><body><span data-ua="Україна">keep</span><script id="other">keep();</script>'
        html+='<!-- UA-SITE-COUNTERS-123:START -->\n<script id="ua-site-counters-123">\n'+before_script+'\n</script>\n'
        html+='<!-- UA-SITE-COUNTERS-123:END --></body></html>'
        changed,proof=patcher.patch_html_client(html,self.original,self.candidate)
        self.assertEqual(changed,html.replace(before_script,self.counter.CLIENT_SCRIPT,1))
        self.assertEqual(proof['status'],'PATCHED_EXACT_SCRIPT')
        again,proof=patcher.patch_html_client(changed,self.original,self.candidate)
        self.assertEqual(again,changed)
        self.assertEqual(proof['status'],'ALREADY_CURRENT')

    def test_absent_inline_script_does_not_inject_or_change_layout(self):
        html=document(card(contents='<span data-ua="Україна">caption</span>'))
        result,proof=patcher.patch_html_client(html,self.original,self.candidate)
        self.assertEqual(result,html)
        self.assertEqual(proof['status'],'ABSENT_UNCHANGED')

    def test_unknown_duplicate_or_broken_inline_counter_script_fails_closed(self):
        script='<script id="ua-site-counters-123">'+self.counter.CLIENT_SCRIPT+'</script>'
        for html in (script+script,script.replace('const aliases','const unexpected'),
                     '<!-- UA-SITE-COUNTERS-123:START -->',
                     '<script id="ua-site-counters-123">unterminated'):
            with self.assertRaises(ValueError):
                patcher.patch_html_client(html,self.original,self.candidate)

    def test_inline_migration_rejects_source_and_candidate_drift(self):
        with self.assertRaisesRegex(ValueError,'SOURCE_SHA256_MISMATCH'):
            patcher.patch_html_client(document(''),self.original+'\n',self.candidate)
        with self.assertRaisesRegex(ValueError,'AFTERIMAGE_SOURCE_MISMATCH'):
            patcher.patch_html_client(document(''),self.original,self.candidate+'\n')


if __name__=='__main__': unittest.main()
