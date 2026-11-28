#!/usr/bin/env python3
"""ADS-AWTAG-SITE: the V2 tag script run in Node with a minimal page (dataLayer, click and DOMContentLoaded handlers,
the order receipt observer, sessionStorage). One Google Ads conversion follows each generate_lead: the order form,
the Telegram hand-off and quick-lead.js's own call (taken from the live copy); contacts and the GA4 events stay."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import candidate_builder as cb  # noqa: E402

QUICK = HERE.parent/'korea_lots_page_001/fixtures/quick-lead_live.js'
SCRIPT = re.compile(r'<script>(.*?)</script>', re.S)

HARNESS = r"""
const vm = require('vm');
const [tag, quickCall] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const handlers = {}, observers = [], store = {};
const receipt = {hidden: true};
const sandbox = {
  Date, JSON,
  sessionStorage: {getItem: k => store[k] || null, setItem: (k, v) => { store[k] = String(v); }},
  document: {
    addEventListener: (type, fn) => { (handlers[type] = handlers[type] || []).push(fn); },
    querySelector: sel => sel === '#ua-order #receipt' ? receipt : null,
  },
  MutationObserver: function (fn) { this.observe = () => observers.push(fn); },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(tag, sandbox);
const fire = (type, event) => (handlers[type] || []).forEach(fn => fn(event));
const element = (selector, href) => ({closest: s => (s === selector ? {getAttribute: () => href} : null)});
const steps = {};
const log = () => sandbox.dataLayer.map(a => Array.from(a));
let seen = 0;
const step = name => { const all = log(); steps[name] = all.slice(seen); seen = all.length; };
step('load');
fire('DOMContentLoaded', {});
receipt.hidden = false; observers.forEach(fn => fn()); step('order_form');
observers.forEach(fn => fn()); step('order_form_again');
fire('click', {target: element('#ua-order #handoff')}); step('handoff');
fire('click', {target: element('a[href]', 'tel:+380000000000')}); step('phone');
vm.runInContext(quickCall, Object.assign(sandbox, {form: {dataset: {model: 'kia-k5'}}})); step('quick_form');
vm.runInContext(quickCall, Object.assign(sandbox, {form: {dataset: {car: 'UA-0001'}}})); step('card_form');
process.stdout.write(JSON.stringify(steps));
"""


def quick_call():
    """quick-lead.js's generate_lead statement, as published."""
    source = QUICK.read_text(encoding='utf-8')
    match = re.search(r"if \(window\.gtag\) gtag\('event', 'generate_lead'.*?\);", source, re.S)
    if not match:
        raise AssertionError('QUICK_LEAD_CALL_MISSING')
    return match.group(0)


@unittest.skipUnless(shutil.which('node'), 'node is not installed')
class TagScriptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts = SCRIPT.findall(cb.NEW.SNIPPET)
        if len(scripts) != 1:
            raise AssertionError('TAG_SCRIPT')
        result = subprocess.run(['node', '-e', HARNESS], input=json.dumps([scripts[0], quick_call()]),
                                capture_output=True, text=True, timeout=60, check=False)
        if result.returncode != 0:
            raise AssertionError(result.stderr[-800:])
        cls.steps = json.loads(result.stdout)

    def conversions(self, step):
        return [e for e in self.steps[step] if e[:2] == ['event', 'conversion']]

    def test_config_ga4_and_ads(self):
        self.assertEqual(self.steps['load'][0][0], 'js')
        self.assertEqual(self.steps['load'][1:], [['config', 'G-6SRBQK6GY4'], ['config', 'AW-18537441937']])

    def test_one_conversion_after_each_lead(self):
        conversion = ['event', 'conversion', {'send_to': 'AW-18537441937/fvkWCIT9vsAdEJHVq4dF'}]
        expected = {'order_form': {'method': 'order_form'}, 'handoff': {'method': 'order_telegram'},
                    'quick_form': {'method': 'quick_form', 'model': 'kia-k5'},
                    'card_form': {'method': 'card_form', 'car': 'UA-0001'}}
        for step, params in expected.items():
            self.assertEqual(self.steps[step], [['event', 'generate_lead', params], conversion], step)

    def test_no_conversion_without_a_lead(self):
        self.assertEqual(self.steps['order_form_again'], [])  # the receipt counts once per session, as in V1
        self.assertEqual(self.steps['phone'], [['event', 'contact', {'method': 'phone'}]])
        self.assertEqual(self.conversions('load'), [])


if __name__ == '__main__':
    unittest.main()
