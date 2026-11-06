// Short enquiry: name + phone (filled by the phone's own autofill) and the model, sent to the existing
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
[REDACTED]
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