/* SHARE-LOTS-001: «Поделиться» in the opened auction lot card (dialog #kl-card) — one file for Korea, Japan and USA.
   Phone: Web Share API (navigator.share). Elsewhere, or when sharing fails: Telegram / WhatsApp / copy the link.
   The link is the country page + #lot-ID, which opens the page with that car (the page already handles the hash). */
(function () {
  'use strict';
  var card = document.getElementById('kl-card');
  if (!card || card.querySelector('.ls-btn')) return;
  var WORDS = {
    uk: ['Поділитися', 'Поділитися автомобілем', 'Скопіювати посилання', 'Закрити', 'Посилання на автомобіль скопійовано'],
    ru: ['Поделиться', 'Поделиться автомобилем', 'Скопировать ссылку', 'Закрыть', 'Ссылка на автомобиль скопирована'],
    ka: ['გაზიარება', 'ავტომობილის გაზიარება', 'ბმულის კოპირება', 'დახურვა', 'ავტომობილის ბმული დაკოპირდა']
  };
  function words() { return WORDS[document.documentElement.lang] || WORDS.uk; }
  function link() {
    var m = /^#lot-[\w-]+$/.exec(location.hash);
    return location.origin + location.pathname + (m ? m[0] : '');
  }
  function title() {
    var h = card.querySelector('#kl-card-body h3');
    return (h ? h.textContent.trim() + ' · ' : '') + 'UA ART COMPANY';
  }

  var style = document.createElement('style');
  style.textContent =
    '.ls-btn{position:absolute;z-index:1;top:4px;right:108px;width:44px;height:44px;border:0;padding:0;border-radius:50%;' +
    'background:#f0a63c;color:#10161f;display:flex;align-items:center;justify-content:center;cursor:pointer;' +
    'box-shadow:0 2px 10px rgba(0,0,0,.35)}.ls-btn:active{background:#d8912f}' +
    '.ls-menu{width:min(420px,92vw);border:0;border-radius:18px;padding:18px 16px 12px;background:#152437;color:#fff;text-align:center}' +
    '.ls-menu::backdrop{background:rgba(0,0,0,.55)}.ls-menu h4{margin:0 0 6px;font-size:17px}' +
    '.ls-item{display:block;width:100%;box-sizing:border-box;padding:15px 12px;margin-top:8px;border:0;border-radius:14px;' +
    'background:rgba(255,255,255,.08);color:#fff;font:inherit;font-size:16px;text-decoration:none;cursor:pointer}' +
    '.ls-close{background:transparent;opacity:.65}' +
    '.ls-toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:#f0a63c;color:#10161f;font-weight:700;' +
    'font-size:14px;padding:11px 18px;border-radius:12px;z-index:2;display:none}';
  document.head.appendChild(style);

  var btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'ls-btn';
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v13"/><path d="M7.5 7.5 12 3l4.5 4.5"/>' +
    '<path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"/></svg>';
  var toast = document.createElement('div');
  toast.className = 'ls-toast';
  toast.setAttribute('role', 'status');
  var menu = document.createElement('dialog');
  menu.className = 'ls-menu';
  card.appendChild(btn);
  card.appendChild(toast);
  document.body.appendChild(menu);

  function label() { var w = words(); btn.setAttribute('aria-label', w[0]); btn.title = w[0]; }
  label();
  new MutationObserver(label).observe(document.documentElement, {attributes: true, attributeFilter: ['lang']});

  function openMenu(data) {
    var w = words(), u = encodeURIComponent(data.url), t = encodeURIComponent(data.title);
    menu.innerHTML = '<h4></h4>' +
      '<a class="ls-item" target="_blank" rel="noopener" href="https://t.me/share/url?url=' + u + '&text=' + t + '">Telegram</a>' +
      '<a class="ls-item" target="_blank" rel="noopener" href="https://wa.me/?text=' + t + '%20' + u + '">WhatsApp</a>' +
      '<button type="button" class="ls-item" data-ls="copy"></button>' +
      '<button type="button" class="ls-item ls-close" data-ls="close"></button>';
    menu.querySelector('h4').textContent = w[1];
    menu.querySelector('[data-ls="copy"]').textContent = w[2];
    menu.querySelector('[data-ls="close"]').textContent = w[3];
    menu.showModal();
  }
  function copied() {
    menu.close();
    toast.textContent = words()[4];
    toast.style.display = 'block';
    setTimeout(function () { toast.style.display = 'none'; }, 2200);
  }
  function copy(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(copied, function () { legacyCopy(text); });
    } else {
      legacyCopy(text);
    }
  }
  function legacyCopy(text) {
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.cssText = 'position:absolute;left:-9999px';
    menu.appendChild(area);
    area.select();
    try { document.execCommand('copy'); } catch (e) {}
    menu.removeChild(area);
    copied();
  }

  var current = null;
  menu.addEventListener('click', function (e) {
    var act = e.target.closest && e.target.closest('[data-ls]');
    if (e.target === menu || (act && act.getAttribute('data-ls') === 'close')) menu.close();
    else if (act && current) copy(current.url);
  });
  btn.addEventListener('click', function () {
    current = {title: title(), url: link()};
    if (navigator.share && (!navigator.canShare || navigator.canShare(current))) {
      navigator.share(current).catch(function (e) { if (!e || e.name !== 'AbortError') openMenu(current); });
    } else {
      openMenu(current);
    }
  });
}());
