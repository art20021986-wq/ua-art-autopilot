
/* UA-ART-PUBLIC-PRICES-V1: independent published CRM prices. */
(function () {
  'use strict';
  if (window.__uaArtPublicPricesV1) return;
  window.__uaArtPublicPricesV1 = true;
  function element(html) {
    var template = document.createElement('template'); template.innerHTML = html;
    return template.content.querySelector('.ua-market-prices-v1');
  }
  function replace(slot, html) {
    if (!slot || slot.getAttribute('data-price-source') === html) return;
    var node = element(html); if (!node) return;
    node.setAttribute('data-price-source', html); slot.replaceWith(node);
  }
  function apply(data) {
    if (!data || data.version !== 1 || !data.cars) return;
    document.querySelectorAll('article.catalog-card').forEach(function (card) {
      var top = card.querySelector('.catalog-top'), id = top && top.querySelector(':scope > span');
      var code = id && id.textContent.trim(), price = data.cars[code];
      if (!price) return;
      replace(top.querySelector(':scope > .ua-market-prices-v1') || top.querySelector(':scope > b'), price.compact);
    });
    var match = location.pathname.match(/\/(UA-[0-9]{4})\.html$/);
    if (match && data.cars[match[1]]) {
      var existing = document.querySelector('.ua-market-prices-v1');
      if (existing) { replace(existing,data.cars[match[1]].full); return; }
      var modern = document.querySelector('.cn');
      if (modern && modern.querySelector('.cn_b') && modern.querySelector('.cn_p')) {
        var node = element(data.cars[match[1]].full);
        if (node) { node.setAttribute('data-price-source',data.cars[match[1]].full); modern.querySelector('.cn_b').replaceWith(node); modern.querySelector('.cn_p').remove(); }
      } else {
        var old = document.querySelector('.cena');
        if (old) {
          var caption = old.nextElementSibling;
          replace(old,data.cars[match[1]].full);
          if (caption && (caption.classList.contains('tiho') || caption.classList.contains('tihо'))) caption.remove();
        }
      }
    }
  }
  var busy = false;
  function refresh() {
    if (busy || document.hidden) return; busy = true;
    fetch('/ua-art-public-prices-v1.json',{credentials:'omit',cache:'no-store'})
      .then(function (response) { if (!response.ok) throw new Error('prices unavailable'); return response.json(); })
      .then(apply).catch(function () {}).finally(function () { busy = false; });
  }
  function start() {
    if (!document.querySelector('article.catalog-card,.cena,.cn')) return;
    refresh(); window.setInterval(refresh,60000);
    window.addEventListener('pageshow',refresh);
    document.addEventListener('visibilitychange',refresh);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',start,{once:true}); else start();
})();
