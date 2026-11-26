/* USA turnkey calculator (SEARCH-HOME-001). Plain JS, no libraries.
   Reads /video/usa/tariffs.json (weekly copy, see usa_tariffs_sync.py); search box = WAI-ARIA APG combobox
   (https://www.w3.org/WAI/ARIA/apg/patterns/combobox/). Texts follow <html lang> like the rest of the site. */
(function () {
  'use strict';
  var box = document.getElementById('usa-calc');
  if (!box) return;
  var input = document.getElementById('usa-where'), list = document.getElementById('usa-yards'),
      out = document.getElementById('usa-result'), kinds = box.querySelectorAll('[data-kind]');
  var W = {
    uk: {total: 'Доставка до Києва під ключ', plus: '+ ціна авто на аукціоні та розмитнення',
         inc: 'Що входить у', ship: 'Доставка зі США до Грузії, страхування', buy: 'Викуп з аукціону',
         port: 'Портові витрати в Грузії', truck: 'Грузія → Київ', service: 'Послуга UA ART',
         exp: 'Авто дорожче 15 000 $ — ще +1% від ціни авто (страхування)', pick: 'Почніть вводити місто — оберіть майданчик зі списку',
         other: 'Мото, квадроцикл, вантажне — ціну порахує менеджер', none: 'Не знайшли — напишіть менеджеру',
         date: 'Ціни оновлено'},
    ru: {total: 'Доставка до Киева под ключ', plus: '+ цена авто на аукционе и растаможка',
         inc: 'Что входит в', ship: 'Доставка из США в Грузию, страхование', buy: 'Выкуп с аукциона',
         port: 'Портовые расходы в Грузии', truck: 'Грузия → Киев', service: 'Услуга UA ART',
         exp: 'Авто дороже 15 000 $ — ещё +1% от цены авто (страхование)', pick: 'Начните вводить город — выберите площадку из списка',
         other: 'Мото, квадроцикл, грузовое — цену посчитает менеджер', none: 'Не нашли — напишите менеджеру',
         date: 'Цены обновлены'},
    ka: {total: 'მიწოდება კიევამდე სრული მომსახურებით', plus: '+ ავტომობილის ფასი აუქციონზე და განბაჟება',
         inc: 'რას მოიცავს', ship: 'მიწოდება აშშ-დან საქართველომდე, დაზღვევა', buy: 'აუქციონიდან გამოსყიდვა',
         port: 'პორტის ხარჯები საქართველოში', truck: 'საქართველო → კიევი', service: 'UA ART მომსახურება',
         exp: '15 000 $-ზე ძვირი ავტომობილი — +1% ფასიდან (დაზღვევა)', pick: 'დაიწყეთ ქალაქის შეყვანა — აირჩიეთ სიიდან',
         other: 'მოტო, კვადროციკლი, სატვირთო — ფასს მენეჯერი დაითვლის', none: 'ვერ იპოვეთ — მიწერეთ მენეჯერს',
         date: 'ფასები განახლდა'}
  };
  var data = null, yard = null, kind = 'car', active = -1, shown = [];

  function words() { return W[document.documentElement.lang] || W.uk; }
  function money(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' $'; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function label(y) { return y[0] + ', ' + y[1]; }

  function render() {
    var w = words();
    if (kind === 'other') { out.innerHTML = '<p>' + w.other + '</p>'; return; }
    if (!yard) { out.innerHTML = '<p>' + w.pick + '</p>'; return; }
    var c = data.costs, ship = kind === 'suv' ? yard[3] : yard[2];
    var rows = [[w.ship, ship], [w.buy, c.buy], [w.port, c.port], [w.truck, c.truck], [w.service, c.service]];
    var sum = rows.reduce(function (s, r) { return s + r[1]; }, 0);
    out.innerHTML = '<div class="tot"><span>' + w.total + '</span><b>' + money(sum) + '</b><small>' + w.plus + '</small></div>' +
      '<details><summary>' + w.inc + ' ' + money(sum) + '</summary><div class="res">' +
      rows.map(function (r) { return '<div><span>' + r[0] + '</span><b>' + money(r[1]) + '</b></div>'; }).join('') +
      '</div><p>' + w.exp + '</p><p>' + w.date + ': ' + esc(data.updated) + '</p></details>';
  }

  function close() { list.hidden = true; input.setAttribute('aria-expanded', 'false'); input.removeAttribute('aria-activedescendant'); active = -1; }
  function mark(i) {
    active = i;
    Array.prototype.forEach.call(list.children, function (li, n) { li.setAttribute('aria-selected', String(n === i)); });
    if (i >= 0) { input.setAttribute('aria-activedescendant', list.children[i].id); list.children[i].scrollIntoView({block: 'nearest'}); }
  }
  function choose(i) { yard = shown[i]; input.value = label(yard); close(); render(); }

  function suggest() {
    var q = input.value.trim().toLowerCase();
    yard = null;
    if (q.length < 2) { close(); render(); return; }
    var parts = q.split(/[\s,]+/);
    shown = data.yards.filter(function (y) {
      var hay = (y[0] + ' ' + y[1] + ' ' + y[4]).toLowerCase();
      return parts.every(function (p) { return hay.indexOf(p) >= 0; });
    }).slice(0, 8);
    list.innerHTML = shown.length ? shown.map(function (y, i) {
      return '<li id="usa-y' + i + '" role="option" aria-selected="false"><b>' + esc(y[0]) + '</b>, ' + esc(y[1]) + '</li>';
    }).join('') : '<li role="option" aria-disabled="true">' + words().none + '</li>';
    list.hidden = false; input.setAttribute('aria-expanded', 'true'); mark(-1); render();
  }

  input.addEventListener('input', suggest);
  input.addEventListener('keydown', function (e) {
    if (list.hidden || !shown.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); mark((active + 1) % shown.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); mark((active - 1 + shown.length) % shown.length); }
    else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); choose(active); }
    else if (e.key === 'Escape') { close(); }
  });
  input.addEventListener('blur', function () { setTimeout(close, 150); });
  list.addEventListener('mousedown', function (e) {
    var li = e.target.closest('[role=option]'); if (!li || !li.id) return;
    e.preventDefault(); choose(Array.prototype.indexOf.call(list.children, li));
  });
  Array.prototype.forEach.call(kinds, function (b) {
    b.addEventListener('click', function () {
      kind = b.getAttribute('data-kind');
      Array.prototype.forEach.call(kinds, function (x) { x.setAttribute('aria-pressed', String(x === b)); });
      render();
    });
  });
  function placeholder() { input.placeholder = input.getAttribute('data-ph-' + document.documentElement.lang) || input.getAttribute('data-ph-uk'); }
  new MutationObserver(function () { placeholder(); if (data) render(); })
    .observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});

  fetch('/video/usa/tariffs.json', {cache: 'no-cache'}).then(function (r) { if (!r.ok) throw r.status; return r.json(); })
    .then(function (d) { data = d; box.hidden = false; placeholder(); render(); })
    .catch(function () { /* no prices: the calculator stays hidden, the lead button still works */ });
}());
