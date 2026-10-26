"""Static assets of the short enquiry form, published as /video/order/quick-lead.js and quick-lead.css.

Kept as text in a Python module because the release pipeline ships only Python files (as home_photos.py).
"""
JS = r'''// Short enquiry on a model page: name + phone (filled by the phone's own autofill), the page's model,
// sent to the existing order API as ua_order_request.quick.v1. Texts come from the form's data-* attributes.
(function () {
  'use strict';
  var form = document.querySelector('form[data-ua-quick-lead]');
  if (!form || !window.fetch) return;
  var status = form.querySelector('[data-status]');
  var consent = form.querySelector('[data-consent]');
  var button = form.querySelector('button');
  var requestId = (window.crypto && crypto.randomUUID) ? crypto.randomUUID() : '';
  var session = fetch('/api/orders/bootstrap', {credentials: 'same-origin'}).then(function (response) {
    if (!response.ok) throw new Error('bootstrap');
    return response.json();
  });
  session.then(function (data) {
    var text = data.consent_text && data.consent_text[form.dataset.lang];
    if (text) consent.textContent = text;
  }).catch(function () {});

  function show(message) { status.textContent = message; status.hidden = false; }

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
        lang: form.dataset.lang, source_path: location.pathname,
        consent: {accepted: true, version: data.consent_version}
      };
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
        throw new Error(field === 'contact' ? 'phone' : field === 'customer_name' ? 'name' : 'error');
      }
      form.querySelector('[data-fields]').hidden = true;
      show(form.dataset.ok.replace('{number}', result.body.number));
      if (window.gtag) gtag('event', 'generate_lead', {method: 'quick_form', model: form.dataset.model});
    }).catch(function (error) {
      button.disabled = false;
      show(error.message === 'phone' ? form.dataset.badPhone : error.message === 'name' ? form.dataset.badName
           : form.dataset.error);
    });
  });
})();
'''

CSS = '''.ua-quick{margin:18px 0 26px;padding:18px 16px;border:1px solid rgba(240,166,60,.45);border-radius:16px;background:#0f2137}
.ua-quick h2{margin:0 0 12px;font-size:20px}
.ua-quick label{display:block;margin:0 0 12px;font-size:14px;color:#aebed0}
.ua-quick input{display:block;box-sizing:border-box;width:100%;margin-top:6px;padding:13px 14px;border:1px solid #728292;border-radius:12px;background:#0B1524;color:#e8eef8;font-size:17px}
.ua-quick button{display:block;width:100%;padding:15px 16px;border:0;border-radius:14px;background:#f0a63c;color:#10161f;font-weight:800;font-size:17px;cursor:pointer}
.ua-quick button:disabled{opacity:.6}
.ua-quick .note{margin:10px 0 0;font-size:14px;color:#e8eef8}
.ua-quick .consent{margin:8px 0 0;font-size:12px;line-height:1.4;color:#aebed0}
.ua-quick .status{margin:12px 0 0;font-weight:700}
'''
