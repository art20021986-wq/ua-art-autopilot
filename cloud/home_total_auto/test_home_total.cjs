/* Behavioral tests with mocked DOM objects, not a real browser/HTML parser.
 * Run: node cloud/home_total_auto/test_home_total.cjs
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, 'home_total.js'), 'utf8');
const CTA = '.outline-cta i[data-ru*="Открыть все автомобили"]';

class Node {
  constructor(tag, attrs = {}, children = []) {
    this.tag = tag; this.attrs = {...attrs}; this.children = children; this.textContent = '';
    for (const child of children) child.parent = this;
  }
  getAttribute(name) { return this.attrs[name] ?? null; }
  setAttribute(name, value) {
    const changed = this.attrs[name] !== value;
    this.attrs[name] = value;
    if (changed && this.observer?.options.attributeFilter.includes(name)) this.observer.callback();
  }
  matches(selector) {
    const match = selector.match(/^([a-z]+)?(?:\.([\w-]+))?(?:\[([\w-]+)\])?$/);
    if (!match) throw new Error('Unsupported mocked selector: ' + selector);
    return (!match[1] || this.tag === match[1]) &&
      (!match[2] || (this.attrs.class || '').split(/\s+/).includes(match[2])) &&
      (!match[3] || this.getAttribute(match[3]) !== null);
  }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []),
      ...child.querySelectorAll(selector)]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  closest(selector) { return this.matches(selector) ? this : this.parent?.closest(selector) || null; }
}
const el = (tag, attrs, children) => new Node(tag, attrs, children);
const id = n => 'UA-' + String(n).padStart(4, '0');
function card(n, format = 'nested', stage = 'korea') {
  const attrs = {class: 'catalog-card', 'data-stage': stage};
  if (format === 'root') attrs['data-ua'] = ' ' + id(n).toLowerCase() + ' ';
  const children = format === 'nested' ? [el('div', {'data-ua-card': id(n)})] : [];
  if (format === 'href') children.push(el('a', {href: id(n) + '.html?lang=uk'}));
  return el('article', attrs, children);
}
function catalog(cards) {
  return el('html', {}, [el('div', {class: 'catalog-grid'}, cards),
    el('footer', {}, [el('a', {href: 'UA-9999.html'})])]);
}
const settle = () => new Promise(resolve => setImmediate(resolve));
function harness(initial, href = '/inventory/katalog.html?f=korea&etap=3&stage=other&lang=uk#cars') {
  const cta = el('i', {'data-ru': 'Открыть все автомобили · 16',
    'data-uk': 'Відкрити всі автомобілі · 16', 'data-ua-home-total': 'v1'});
  cta.textContent = cta.attrs['data-uk'];
  const stage = el('div', {class: 'stage-card', 'data-stage': 'korea', 'data-count': '4'},
    [el('em', {'data-ru': '4 автомобиля', 'data-uk': '4 автомобілі'})]);
  const root = el('html', {lang: 'uk'}, [el('a', {class: 'outline-cta', href}, [cta]), stage]);
  const doc = {readyState: 'complete', baseURI: 'https://uaart.com.ua/home/index.html',
    documentElement: root, querySelector: selector => selector === CTA ? cta : root.querySelector(selector)};
  const env = {cta, stage, root, catalog: initial, requests: [], warnings: [], events: {},
    status: 200, type: 'text/html; charset=utf-8', responseURL: ''};
  const context = {document: doc, location: new URL(doc.baseURI), URL,
    MutationObserver: class {
      constructor(callback) { this.callback = callback; }
      observe(node, options) { node.observer = {callback: this.callback, options}; }
    },
    DOMParser: class { parseFromString() { return env.catalog; } },
    console: {warn: (...args) => env.warnings.push(args)},
    fetch: async (url, options) => {
      env.requests.push({url, options});
      if (env.error) throw new Error(env.error);
      return {ok: env.status === 200, status: env.status, url: env.responseURL,
        headers: {get: () => env.type}, text: async () => env.html || '<html><body>mocked catalogue DOM</body></html>'};
    },
    addEventListener: (name, handler) => { env.events[name] = handler; }
  };
  context.window = context;
  env.run = () => vm.runInNewContext(source, context);
  env.refresh = async () => { env.events.pageshow({persisted: true}); await settle(); };
  env.snapshotStage = () => JSON.stringify({attrs: stage.attrs, child: stage.children[0].attrs});
  return env;
}

(async () => {
  const cars = Array.from({length: 18}, (_, i) => card(i + 1,
    i === 0 ? 'root' : i === 1 ? 'href' : 'nested', i >= 16 ? 'unknown-stage' : 'korea'));
  const env = harness(catalog(cars));
  const stageBefore = env.snapshotStage();
  env.run(); await settle();
  assert.equal(env.cta.textContent, 'Відкрити всі автомобілі · 18');
  assert.equal(env.cta.attrs['data-ru'], 'Открыть все автомобили · 18');
  const requested = new URL(env.requests[0].url);
  assert.equal(requested.pathname, '/inventory/katalog.html');
  assert.equal(requested.search, '?lang=uk');
  assert.equal(requested.hash, '');
  assert.equal(env.requests[0].options.cache, 'no-store');
  assert.equal(env.requests[0].options.credentials, 'same-origin');
  env.catalog = catalog([...cars, card(19)]); await env.refresh();
  assert.match(env.cta.textContent, /19$/);
  env.catalog = catalog(cars); await env.refresh();
  assert.match(env.cta.textContent, /18$/);
  env.catalog = catalog([...cars, card(1), el('a', {'data-ua-card': id(2), href: id(2) + '.html'})]);
  await env.refresh(); assert.match(env.cta.textContent, /18$/);
  env.root.setAttribute('lang', 'ru');
  assert.equal(env.cta.textContent, 'Открыть все автомобили · 18');
  env.root.setAttribute('lang', 'uk-UA');
  assert.equal(env.cta.textContent, 'Відкрити всі автомобілі · 18');

  for (const bad of [el('html'), catalog([...cars, card(20, 'missing')]),
    catalog([el('article', {class: 'catalog-card', 'data-ua': id(1)},
      [el('div', {'data-ua-card': id(2)})])]),
    catalog([el('article', {class: 'catalog-card'},
      [el('a', {href: 'https://elsewhere.test/UA-0020.html'})])])]) {
    env.catalog = bad; await env.refresh(); assert.match(env.cta.textContent, /18$/);
  }
  env.catalog = catalog(cars);
  env.status = 503; await env.refresh(); assert.match(env.cta.textContent, /18$/);
  env.status = 200; env.type = 'application/json'; await env.refresh(); assert.match(env.cta.textContent, /18$/);
  env.type = 'text/html'; env.error = 'Network unavailable'; await env.refresh(); assert.match(env.cta.textContent, /18$/);
  delete env.error; env.responseURL = 'https://elsewhere.test/katalog.html';
  await env.refresh(); assert.match(env.cta.textContent, /18$/); env.responseURL = '';
  env.html = '<html><body>truncated catalogue';
  await env.refresh(); assert.match(env.cta.textContent, /18$/); delete env.html;
  assert.equal(env.warnings.length, 9);
  env.catalog = catalog([]); await env.refresh(); assert.match(env.cta.textContent, /0$/);
  env.catalog = catalog([el('a', {'data-ua-card': id(7), href: 'UA-0007.html'})]);
  await env.refresh(); assert.match(env.cta.textContent, /1$/);
  assert.equal(env.snapshotStage(), stageBefore);
  const requestCount = env.requests.length;
  env.events.pageshow({persisted: false}); env.run(); await settle();
  assert.equal(env.requests.length, requestCount, 'No duplicate startup request or ordinary pageshow fetch');
  const failure = harness(el('html')); failure.run(); await settle();
  assert.match(failure.cta.textContent, /16$/, 'Initial server value survives invalid response');
  const external = harness(catalog(cars), 'https://elsewhere.test/katalog.html');
  external.run(); await settle(); assert.equal(external.requests.length, 0);
  assert.match(external.cta.textContent, /16$/);
  console.log('PASS: 18/19/18, unknown stages, unique IDs, legacy/root/href formats, invalid responses, language, empty catalogue, bfcache and unchanged stage nodes (mocked DOM).');
})().catch(error => { console.error(error); process.exitCode = 1; });
