"""Ad source of a visit, published as /video/order/attribution.js (ADS-READY-001).

Kept as text in a Python module because the release pipeline ships only Python files (as quick_assets.py).
Loaded by the order page and the model pages, the pages Google Ads links to. It reads the Google Ads click
ids and utm tags of the landing URL and keeps them in this browser for 90 days (the Google Ads click
window); a later visit with new tags replaces them, one without tags keeps them. The enquiry forms send
window.uaAttribution() with the request; the server keeps the clean values (ua_order/attribution.py).
"""
JS = r'''// Ad source of this visit for the site's enquiry forms: Google Ads click ids and utm tags of the landing URL.
(function () {
  'use strict';
  var KEY = 'ua_attribution';
  var DAYS = 90;
  var NAMES = ['gclid', 'gbraid', 'wbraid', 'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content'];
  var params = new URLSearchParams(location.search);
  var found = {};
  NAMES.forEach(function (name) {
    var value = params.get(name);
    if (value) found[name] = value.slice(0, 200);
  });
  var tagged = Object.keys(found).length > 0;
  if (tagged) {
    try { localStorage.setItem(KEY, JSON.stringify({values: found, expires: Date.now() + DAYS * 864e5})); } catch (e) {}
  }
  window.uaAttribution = function () {
    if (tagged) return found;
    try {
      var kept = JSON.parse(localStorage.getItem(KEY));
      return kept && kept.expires > Date.now() ? kept.values : null;
    } catch (e) { return null; }
  };
})();
'''
