"""Korea lot window photo viewer (KOREA-GALLERY-001, owner 2026-11-13): as on the catalogue car cards.

A large photo on top, a strip of thumbnails below, arrows, swipe, keyboard, «Фото N / M». Same markup classes and
styles as the catalogue gallery (ua_media_styles.CSS), so both look alike; the catalogue script itself is not used
because it starts once per page load and the lot window is drawn later.

The page draws a lot into #kl-card-body with a .kl-photos strip (the list's first photos); this script replaces
the strip with the viewer and adds the lot's other photos from its gallery file
(/video/korea/gallery/<id>.json). No file or an error: the viewer keeps the first photos.
"""
JS = r'''
(() => {
  'use strict';
  const body = document.getElementById('kl-card-body');
  if (!body || !window.MutationObserver) return;
  const words = {
    uk: ['Фото','Назад','Далі','Фотографії автомобіля','Завантаження…','Не вдалося завантажити фото'],
    ru: ['Фото','Назад','Вперёд','Фотографии автомобиля','Загрузка…','Не удалось загрузить фото'],
    ka: ['ფოტო','წინა','შემდეგი','ავტომობილის ფოტოები','იტვირთება…','ფოტო ვერ ჩაიტვირთა']
  };
  function locale() {
    const selected = document.querySelector('.ua-site-lang [aria-pressed="true"]');
    return words[(selected && selected.getAttribute('data-lang')) || document.documentElement.lang] || words.uk;
  }
  function el(tag, cls, attrs) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    Object.keys(attrs || {}).forEach(k => node.setAttribute(k, attrs[k]));
    return node;
  }
  let current = null;
  function viewer(strip) {
    const lead = body.querySelector('[data-quick-lead-lot]');
    const id = lead ? lead.getAttribute('data-quick-lead-lot') : '';
    const head = body.querySelector('h3');
    const title = head ? head.textContent : '';
    const photos = Array.from(strip.querySelectorAll('img')).map(img => img.getAttribute('src'));
    if (!photos.length) return;
    const root = el('section', 'um-gallery kg-gallery', {'aria-roledescription': 'carousel'});
    const view = el('div', 'um-view');
    const bar = el('div', 'um-toolbar');
    const counter = el('span', 'um-counter', {role: 'status', 'aria-live': 'polite', 'aria-atomic': 'true'});
    const stage = el('div', 'um-stage');
    const panel = el('div', 'um-panel', {role: 'tabpanel', id: 'kg-panel'});
    const frame = el('div', 'kg-frame');
    const state = el('div', 'um-state', {hidden: ''});
    const previous = el('button', 'um-tool um-prev', {type: 'button'});
    const next = el('button', 'um-tool um-next', {type: 'button'});
    const rail = el('div', 'um-thumbs', {role: 'tablist'});
    previous.textContent = '‹'; next.textContent = '›';
    state.append(el('span'));
    bar.append(counter); panel.append(frame); stage.append(panel, state, previous, next);
    view.append(bar, stage, rail); root.append(view);
    strip.replaceWith(root);
    let active = 0, tabs = [], swipe = null;
    const g = {id, root};
    current = g;
    function stateOf(value) {
      state.hidden = !value;
      state.firstChild.textContent = value ? locale()[value === 'error' ? 5 : 4] : '';
      panel.setAttribute('aria-busy', String(value === 'loading'));
    }
    function label() {
      const w = locale(), n = photos.length;
      root.setAttribute('aria-label', w[3]); rail.setAttribute('aria-label', w[3]);
      previous.setAttribute('aria-label', w[1]); next.setAttribute('aria-label', w[2]);
      counter.textContent = w[0] + ' ' + (active + 1) + ' / ' + n;
      tabs.forEach((tab, i) => tab.setAttribute('aria-label', w[0] + ' ' + (i + 1) + ' / ' + n));
      const img = frame.firstElementChild;
      if (img) img.alt = title + ' — ' + w[0].toLowerCase() + ' ' + (active + 1);
      previous.disabled = active === 0; next.disabled = active === n - 1;
      previous.hidden = next.hidden = n < 2;
    }
    function show() {
      const img = new Image();
      img.decoding = 'async'; img.draggable = false;
      stateOf('loading');
      img.addEventListener('load', () => {if (frame.firstElementChild === img) stateOf('');});
      img.addEventListener('error', () => {if (frame.firstElementChild === img) stateOf('error');});
      frame.replaceChildren(img);
      img.src = photos[active];
      label();
    }
    function reveal(tab) {
      const left = tab.offsetLeft - rail.offsetLeft;
      if (left < rail.scrollLeft || left + tab.offsetWidth > rail.scrollLeft + rail.clientWidth)
        rail.scrollTo({left: left - (rail.clientWidth - tab.offsetWidth) / 2, behavior: 'auto'});
    }
    function select(index) {
      index = Math.max(0, Math.min(photos.length - 1, index));
      if (index === active && frame.firstElementChild) {reveal(tabs[active]); return;}
      active = index;
      tabs.forEach((tab, i) => {tab.setAttribute('aria-selected', String(i === active)); tab.tabIndex = i === active ? 0 : -1;});
      panel.setAttribute('aria-labelledby', tabs[active].id);
      show(); reveal(tabs[active]);
    }
    function thumbs(from) {
      photos.slice(from).forEach((src, k) => {
        const i = from + k;
        const tab = el('button', 'um-thumb', {type: 'button', role: 'tab', id: 'kg-tab-' + i, 'aria-controls': 'kg-panel',
                                               'aria-selected': String(i === active), tabindex: i === active ? '0' : '-1'});
        tab.dataset.index = String(i);
        const img = el('img', '', {src, alt: '', loading: 'lazy', decoding: 'async', draggable: 'false'});
        img.addEventListener('error', () => {img.hidden = true;});
        const number = el('span', 'um-number', {'aria-hidden': 'true'});
        number.textContent = String(i + 1);
        tab.append(img, number); rail.append(tab); tabs.push(tab);
      });
    }
    thumbs(0);
    panel.setAttribute('aria-labelledby', tabs[0].id);
    show();
    previous.addEventListener('click', () => select(active - 1));
    next.addEventListener('click', () => select(active + 1));
    rail.addEventListener('click', event => {
      const tab = event.target.closest('[role="tab"]');
      if (tab) select(Number(tab.dataset.index));
    });
    rail.addEventListener('keydown', event => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const tab = event.target.closest('[role="tab"]');
      if (!tab) return;
      const i = Number(tab.dataset.index), n = tabs.length;
      const keys = {ArrowRight: (i + 1) % n, ArrowLeft: (i - 1 + n) % n, Home: 0, End: n - 1};
      if (Object.prototype.hasOwnProperty.call(keys, event.key)) {
        event.preventDefault(); event.stopPropagation();
        tabs.forEach((t, j) => {t.tabIndex = j === keys[event.key] ? 0 : -1;});
        tabs[keys[event.key]].focus({preventScroll: true}); reveal(tabs[keys[event.key]]);
      }
    });
    rail.addEventListener('focusout', event => {
      if (!rail.contains(event.relatedTarget)) tabs.forEach((tab, i) => {tab.tabIndex = i === active ? 0 : -1;});
    });
    view.addEventListener('keydown', event => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('.um-thumbs')) return;
      const target = {ArrowLeft: active - 1, ArrowRight: active + 1, Home: 0, End: photos.length - 1};
      if (Object.prototype.hasOwnProperty.call(target, event.key)) {event.preventDefault(); select(target[event.key]);}
    });
    frame.addEventListener('pointerdown', e => {if (e.isPrimary && e.button === 0) swipe = {id: e.pointerId, x: e.clientX, y: e.clientY};});
    frame.addEventListener('pointerup', e => {
      if (!swipe || e.pointerId !== swipe.id) return;
      const dx = e.clientX - swipe.x, dy = e.clientY - swipe.y; swipe = null;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) select(active + (dx < 0 ? 1 : -1));
    });
    frame.addEventListener('pointercancel', () => {swipe = null;});
    g.label = label;
    g.add = more => {
      const from = photos.length;
      more.slice(from).forEach(src => photos.push(src));
      if (photos.length > from) {thumbs(from); label();}
    };
    if (id) fetch('/video/korea/gallery/' + encodeURIComponent(id) + '.json')
      .then(r => r.ok ? r.json() : null)
      .then(data => {if (data && Array.isArray(data.photos) && current === g && g.root.isConnected) g.add(data.photos);})
      .catch(() => {});
  }
  function enhance() {
    const strip = body.querySelector('.kl-photos');
    if (strip) viewer(strip);
  }
  new MutationObserver(enhance).observe(body, {childList: true});
  enhance();
  const language = document.querySelector('.ua-site-lang');
  const relabel = () => {if (current && current.root.isConnected && current.label) current.label();};
  if (language) new MutationObserver(relabel).observe(language, {subtree: true, attributes: true, attributeFilter: ['aria-pressed']});
  new MutationObserver(relabel).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});
})();
'''
