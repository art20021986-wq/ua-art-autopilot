"""Static assets of the short enquiry form, published as /video/order/quick-lead.js and quick-lead.css.

ADS-READY-001: the request carries the ad source kept by attribution.js; the privacy link has its look.

Kept as text in a Python module because the release pipeline ships only Python files (as home_photos.py).
One form contract for both pages: form[data-ua-quick-lead] with data-country/data-model, texts in
hidden [data-msg] elements. On a model page the form is inline; on the order page it sits in a
<dialog> opened by a model card button [data-quick-lead-model].
"""
JS = r'''// Short enquiry: name + phone (filled by the phone's own autofill) and the model, sent to the existing
// order API as ua_order_request.quick.v1.
(function () {
  'use strict';
  var form = document.querySelector('form[data-ua-quick-lead]');
  if (!form || !window.fetch) return;
  var dialog = form.closest('dialog');
  var fields = form.querySelector('[data-fields]');
  var status = form.querySelector('[data-status]');
  var consent = form.querySelector('[data-consent]');
  var button = form.querySelector('button[type=submit]');
  var requestId = '';
  var session = fetch('/api/orders/bootstrap', {credentials: 'same-origin'}).then(function (response) {
    if (!response.ok) throw new Error('bootstrap');
    return response.json();
  });

  function lang() { return form.dataset.lang || document.documentElement.lang || 'uk'; }
  function msg(key) { var el = form.querySelector('[data-msg="' + key + '"]'); return el ? el.textContent : ''; }
  function show(message) { status.textContent = message; status.hidden = false; }
  function fresh() { return (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : ''; }
  function consentText() {
    session.then(function (data) {
      var text = data.consent_text && data.consent_text[lang()];
      if (text) consent.textContent = text;
    }).catch(function () {});
  }
  requestId = fresh();
  consentText();

  if (dialog) {
    document.addEventListener('click', function (event) {
      var opener = event.target.closest && event.target.closest('[data-quick-lead-model]');
      if (opener) {
        form.dataset.model = opener.dataset.quickLeadModel;
        form.dataset.country = opener.dataset.quickLeadCountry;
        form.querySelector('[data-quick-model-title]').textContent = opener.dataset.quickLeadTitle || '';
        requestId = fresh(); fields.hidden = false; status.hidden = true; button.disabled = false;
        consentText();
        dialog.showModal();
        form.elements.namedItem('customer_name').focus();
      } else if (event.target.closest && event.target.closest('[data-quick-close]')) {
        dialog.close();
      }
    });
  }

  form.addEventListener('submit', function (event) {
    event.preventDefault();
    if (!requestId || button.disabled) return;
    button.disabled = true; status.hidden = true;
    session.then(function (data) {
      var payload = {
        schema_version: 'ua_order_request.quick.v1', request_id: requestId, config_version: data.catalog.version,
        purchase_country_code: form.dataset.country, model: form.dataset.model,
        customer_name: form.elements.namedItem('customer_name').value,
        contact: {phone: form.elements.namedItem('phone').value},
        lang: lang(), source_path: location.pathname,
        consent: {accepted: true, version: data.consent_version}
      };
      // The landing page's ad source (attribution.js), when it kept one.
      var source = window.uaAttribution && window.uaAttribution();
      if (source) payload.attribution = source;
      return fetch('/api/orders/submit', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRF-Token': data.csrf},
        body: JSON.stringify(payload)
      });
    }).then(function (response) {
      return response.json().then(function (body) { return {ok: response.ok, body: body}; });
    }).then(function (result) {
      if (!result.ok || result.body.status !== 'saved') {
        var field = result.body.field;
        throw new Error(field === 'contact' ? 'bad_phone' : field === 'customer_name' ? 'bad_name' : 'error');
      }
      fields.hidden = true;
      show(msg('ok').replace('{number}', result.body.number));
      if (window.gtag) gtag('event', 'generate_lead', {method: 'quick_form', model: form.dataset.model});
    }).catch(function (error) {
      button.disabled = false;
      show(msg(['bad_phone', 'bad_name'].indexOf(error.message) >= 0 ? error.message : 'error'));
    });
  });
})();
'''

CSS = '''.ua-quick{margin:18px 0 26px;padding:18px 16px;border:1px solid rgba(240,166,60,.45);border-radius:16px;background:#0f2137;color:#e8eef8}
.ua-quick h2{margin:0 0 12px;font-size:20px}
.ua-quick label{display:block;margin:0 0 12px;font-size:14px;color:#aebed0}
.ua-quick input{display:block;box-sizing:border-box;width:100%;margin-top:6px;padding:13px 14px;border:1px solid #728292;border-radius:12px;background:#0B1524;color:#e8eef8;font-size:17px}
.ua-quick button{display:block;width:100%;padding:15px 16px;border:0;border-radius:14px;background:#f0a63c;color:#10161f;font-weight:800;font-size:17px;cursor:pointer}
.ua-quick button:disabled{opacity:.6}
.ua-quick .note{margin:10px 0 0;font-size:14px;color:#e8eef8}
.ua-quick .consent{margin:8px 0 0;font-size:12px;line-height:1.4;color:#aebed0}
.ua-quick .privacy{display:inline-block;margin:6px 0 0;font-size:12px;color:#aebed0}
.ua-quick .status{margin:12px 0 0;font-weight:700}
.ua-quick-dialog{width:calc(100% - 32px);max-width:480px;padding:0;border:0;background:transparent}
.ua-quick-dialog::backdrop{background:rgba(5,10,18,.75)}
.ua-quick-dialog .ua-quick{margin:0}
.ua-quick .ua-quick-close{margin-top:12px;padding:11px 16px;background:transparent;color:#e8eef8;border:1px solid #728292;font-weight:650;font-size:15px}
.ua-order .model .quick-offer{background:transparent;color:#f0a63c;border-color:#f0a63c}
.ua-order .model .quick-offer+button{margin-top:0}
'''
