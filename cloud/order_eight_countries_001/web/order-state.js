// Pure state transitions shared by the DOM adapter and browser-independent tests.
export const languages = ['uk','ru','ka'];
export function fromUrl(href, countries) {
  const url = new URL(href);
  return {lang:languages.includes(url.searchParams.get('lang')) ? url.searchParams.get('lang') : 'uk',
          country:countries.includes(url.searchParams.get('strana')) ? url.searchParams.get('strana') : ''};
}
export function changeCountry(data, country) {
  return {...data,purchase_country_code:country,model:country===data.purchase_country_code?data.model:''};
}
export function requestPayload(form, catalog, selection, lang, requestId, consentVersion) {
  const contact=form.contact_value.trim();
  return {schema_version:'ua_order_request.v1',request_id:requestId,config_version:catalog.version,
    purchase_country_code:selection.country,model:selection.model,other_model:selection.model?'':form.other_model.trim(),
    budget:{code:form.budget,currency:'USD'},vehicle_type:form.vehicle_type,
    delivery_country:form.delivery_country.trim(),delivery_city:form.delivery_city.trim(),
    customer_name:form.customer_name.trim(),contact:contact.startsWith('@')?{telegram:contact}:{phone:contact},
    comment:form.comment.trim(),lang,source_path:'/video/podbor.html',
    consent:{accepted:form.consent==='on',version:consentVersion}};
}
