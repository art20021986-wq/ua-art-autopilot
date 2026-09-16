/* UA-SITE-COUNTERS-123: one published-catalog snapshot for vehicle counts. */
(function () {
  'use strict';
  const aliases = {kiev:'kiev',kyiv:'kiev',georgia:'georgia',gruzia:'georgia',
    sea:'sea',more:'sea',ferry:'sea',korea:'korea'};
  function snapshot(doc) {
    if (!doc.querySelector('.catalog-grid')) throw Error('Missing catalog grid');
    const records = new Map();
    const cards = Array.from(doc.querySelectorAll('article.catalog-card'));
    doc.querySelectorAll('a[data-ua-card]').forEach(node => {
      if (!node.closest('article.catalog-card')) cards.push(node);
    });
    cards.forEach(card => {
      const ids = new Set(), stages = new Set();
      const nodes = [card, ...card.querySelectorAll('[data-ua-card],[data-category],[data-stage],[data-etap],[data-ua-card-stage]')];
      nodes.forEach(node => {
        ['data-ua-card','data-ua'].forEach(key => {
          const id = (node.getAttribute(key) || '').trim().toUpperCase();
          if (id) { if (!/^UA-[0-9]{4,}$/.test(id)) throw Error('Invalid ID'); ids.add(id); }
        });
        ['data-category','data-stage','data-etap','data-ua-card-stage'].forEach(key => {
          const stage = aliases[(node.getAttribute(key) || '').trim().toLowerCase()];
          if (stage) stages.add(stage);
        });
      });
      if (!ids.size) {
        card.querySelectorAll('a[href]').forEach(link => {
          const href = link.getAttribute('href') || '';
          if (/^(?:https?:)?\/\//i.test(href)) return;
          const match = href.match(/(?:^|\/)(UA-[0-9]{4,})\.html(?:[?#].*)?$/i);
          if (match) ids.add(match[1].toUpperCase());
        });
      }
      if (ids.size !== 1 || stages.size > 1) throw Error('Ambiguous card');
      const id = [...ids][0], stage = [...stages][0] || null;
      if (records.has(id) && records.get(id) !== stage) throw Error('Conflicting duplicate');
      records.set(id, stage);
    });
    const counts = {all:records.size,kiev:0,georgia:0,sea:0,korea:0};
    records.forEach(stage => { if (stage) counts[stage]++; });
    return counts;
  }
  function words(n, uk) {
    const forms = uk ? ['автомобіль','автомобілі','автомобілів'] : ['автомобиль','автомобиля','автомобилей'];
    const d = n % 10, h = n % 100;
    return n + ' ' + forms[d === 1 && h !== 11 ? 0 : d >= 2 && d <= 4 && !(h >= 12 && h <= 14) ? 1 : 2];
  }
  function start() {
    if (window.__uaSiteCounters123) return;
    window.__uaSiteCounters123 = true;
    let last = null, sequence = 0;
    const catalog = !!document.querySelector('.catalog-grid');
    function put(node, ru, uk) {
      node.setAttribute('data-ru', ru); node.setAttribute('data-uk', uk);
      node.textContent = /^(uk|ua)(-|$)/i.test(document.documentElement.lang || '') ? uk : ru;
    }
    function render() {
      if (!last) return;
      document.querySelectorAll('.stage-card[data-stage]').forEach(card => {
        const key = aliases[card.getAttribute('data-stage')];
        if (!key) return;
        const label = card.querySelector('.stage-copy em') || card.querySelector('em');
        card.setAttribute('data-count', String(last[key]));
        if (label) put(label, words(last[key],false), words(last[key],true));
      });
      document.querySelectorAll('.outline-cta i[data-ru*="Открыть все автомобили"]').forEach(node =>
        put(node, 'Открыть все автомобили · ' + last.all, 'Відкрити всі автомобілі · ' + last.all));
      const labels = {all:['Все','Усі'],kiev:['В Киеве','У Києві'],georgia:['В Грузии','У Грузії'],sea:['На пароме','На поромі'],korea:['В Корее','У Кореї']};
      document.querySelectorAll('button[data-f]').forEach(node => {
        const key = node.getAttribute('data-f');
        if (labels[key]) put(node, labels[key][0] + ' · ' + last[key], labels[key][1] + ' · ' + last[key]);
      });
    }
    async function sync() {
      const current = ++sequence;
      try {
        let next;
        if (catalog) next = snapshot(document);
        else {
          const anchor = document.querySelector('.outline-cta[href]');
          if (!anchor) return;
          const url = new URL(anchor.getAttribute('href'), document.baseURI);
          if (url.origin !== location.origin) throw Error('External catalog');
          ['f','stage','etap'].forEach(key => url.searchParams.delete(key));
          url.hash = '';
          const response = await fetch(url.href, {cache:'no-store',credentials:'same-origin'});
          if (!response.ok || !/^text\/html\b/i.test(response.headers.get('content-type') || '')) throw Error('Catalog response');
          if (response.url && new URL(response.url).origin !== location.origin) throw Error('External redirect');
          const source = await response.text();
          if (!/<\/html\s*>\s*$/i.test(source)) throw Error('Incomplete catalog');
          next = snapshot(new DOMParser().parseFromString(source,'text/html'));
        }
        if (current === sequence) { last = next; render(); }
      } catch (error) { console.warn('[UA counters] Keeping last valid counts:', error.message); }
    }
    new MutationObserver(render).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
    window.addEventListener('pageshow', event => {
      if (event.persisted) { if (catalog) location.reload(); else sync(); }
    });
    if (!catalog) document.addEventListener('visibilitychange', () => { if (!document.hidden) sync(); });
    sync();
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = {snapshot,words};
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
}());
