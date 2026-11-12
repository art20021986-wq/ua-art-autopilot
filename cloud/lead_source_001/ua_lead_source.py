"""LEAD-SOURCE-001 (owner 2026-11-12): every site enquiry says where the visitor came from.

attribution.js (ADS-READY-001) kept only the ad click ids and utm tags of the landing URL, and only the order page,
the cards and the model pages loaded it. Now:
- JS (published as /video/order/attribution.js): a visit without tags that came from another site keeps that site
  as the source (Google, Google Карты, Bing, ChatGPT, Facebook, ...); tags still win, and a kept Google Ads click is
  never replaced by an organic visit. The server already stores utm_source/utm_medium and shows them to the owner
  («Источник», «Канал»), so nothing changes there.
- apply(html) loads the script on a page that does not load it yet (home, catalogue, landing pages).
"""
import re

SCRIPT = '<script src="/video/order/attribution.js?v=20261112.1" defer></script>'
HEAD_END = re.compile(r'</head\s*>', re.I)


def has_script(html):
    return 'order/attribution.js' in html


def apply(html):
    """The page with the script before </head>; unchanged if it already loads it or has no head."""
    if not isinstance(html, str) or has_script(html):
        return html
    end = HEAD_END.search(html)
    if not end:
        return html
    return html[:end.start()] + SCRIPT + html[end.start():]


JS = r'''// Source of this visit for the site's enquiry forms (ADS-READY-001, LEAD-SOURCE-001).
(function () {
  'use strict';
  var KEY = 'ua_attribution';
  var DAYS = 90;
  var CLICK_IDS = ['gclid', 'gbraid', 'wbraid'];
  var NAMES = CLICK_IDS.concat(['utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content']);
  // Referring sites by host suffix: [suffix, source, channel]; the first match wins.
  var SITES = [
    ['chatgpt.com', 'ChatGPT', 'ИИ-чат'], ['chat.openai.com', 'ChatGPT', 'ИИ-чат'],
    ['perplexity.ai', 'Perplexity', 'ИИ-чат'], ['gemini.google.com', 'Gemini', 'ИИ-чат'],
    ['copilot.microsoft.com', 'Copilot', 'ИИ-чат'], ['claude.ai', 'Claude', 'ИИ-чат'],
    ['maps.google.com', 'Google Карты', 'карты'], ['maps.app.goo.gl', 'Google Карты', 'карты'],
    ['bing.com', 'Bing', 'поиск'], ['duckduckgo.com', 'DuckDuckGo', 'поиск'], ['yahoo.com', 'Yahoo', 'поиск'],
    ['facebook.com', 'Facebook', 'соцсеть'], ['instagram.com', 'Instagram', 'соцсеть'],
    ['t.me', 'Telegram', 'соцсеть'], ['telegram.org', 'Telegram', 'соцсеть'],
    ['tiktok.com', 'TikTok', 'соцсеть'], ['youtube.com', 'YouTube', 'соцсеть']
  ];

  function read() {
    try {
      var kept = JSON.parse(localStorage.getItem(KEY));
      return kept && kept.expires > Date.now() ? kept.values : null;
    } catch (e) { return null; }
  }

  function keep(values) {
    try { localStorage.setItem(KEY, JSON.stringify({values: values, expires: Date.now() + DAYS * 864e5})); } catch (e) {}
  }

  function ends(host, suffix) {
    return host === suffix || host.slice(-suffix.length - 1) === '.' + suffix;
  }

  function fromReferrer() {
    var url;
    try { url = new URL(document.referrer); } catch (e) { return null; }
    var host = url.hostname.toLowerCase().replace(/^www\./, '');
    if (!host || ends(host, 'uaart.com.ua') || host === location.hostname.replace(/^www\./, '')) return null;
    for (var i = 0; i < SITES.length; i++) {
      if (ends(host, SITES[i][0])) return {utm_source: SITES[i][1], utm_medium: SITES[i][2]};
    }
    if (/(^|\.)google\.[a-z.]+$/.test(host)) {
      return url.pathname.indexOf('/maps') === 0 ? {utm_source: 'Google Карты', utm_medium: 'карты'}
                                                  : {utm_source: 'Google', utm_medium: 'поиск'};
    }
    return {utm_source: host.slice(0, 100), utm_medium: 'сайт'};
  }

  var params = new URLSearchParams(location.search);
  var found = {};
  NAMES.forEach(function (name) {
    var value = params.get(name);
    if (value) found[name] = value.slice(0, 200);
  });
  var tagged = Object.keys(found).length > 0;
  if (tagged) {
    keep(found);
  } else {
    var referred = fromReferrer();
    var kept = read();
    var adClick = kept && CLICK_IDS.some(function (name) { return kept[name]; });
    if (referred && !adClick) keep(referred);
  }

  window.uaAttribution = function () {
    return tagged ? found : (read() || {utm_source: 'Прямой заход'});
  };
})();
'''
