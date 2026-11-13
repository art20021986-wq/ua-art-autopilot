"""OTP Bank credit line in the Korea lot window (LOT-OTP-001, owner 2026-11-12 «Да» on the mockup). No page parsing.

One compact link right under the lot price in the window that opens on a lot: the bank logo, «Перевага OTP: кредит на
авто з аукціону або в дорозі» and a green arrow, to the credit section of the finance page. Only the lot window — the
lot list and search stay as they are (owner). The lot window is filled from lots.json by the page's own lots script;
this separate script watches that window and adds the line to every lot it shows, today's and future ones, without
touching the lots script. Texts in data-uk / data-ru / data-ka like the window's own texts (the site language script
translates them); the Russian site language opens the Russian finance page, the others the Ukrainian one.
"""
import json

MARK = 'ua-lot-otp-001'
TEXT = {'uk': 'Перевага OTP: кредит на авто з аукціону або в дорозі',
        'ru': 'Преимущество OTP: кредит на авто с аукциона или в пути',
        'ka': 'OTP-ის უპირატესობა: კრედიტი აუქციონიდან ან გზაში მყოფ ავტომობილზე'}
PAGE = {'uk': '/video/seo/ua/kredyt-lizynh-avto.html#kredyt', 'ru': '/video/seo/ru/kredit-lizing-avto.html#kredyt'}
LOGO = '/video/finance/otp-bank.png'  # the bank logo already on the site (480×126, white)

CSS = ('<style id="%s">'
       '.kl-otp{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:10px;padding:8px 10px 8px 12px;'
       'border:1px solid rgba(98,196,60,.55);border-radius:12px;color:#d6f5c8;text-decoration:none;font-size:13px;'
       'line-height:1.3;font-weight:700;background:linear-gradient(135deg,rgba(82,174,48,.24),rgba(82,174,48,.07));'
       'box-shadow:inset 0 1px rgba(255,255,255,.08)}'
       '.kl-otp img{display:block;width:58px;height:auto}'
       '.kl-otp-a{width:26px;height:26px;display:grid;place-items:center;border-radius:50%%;background:#52AE30;color:#fff;'
       'transition:transform .2s ease}'
       '.kl-otp:hover .kl-otp-a{transform:translateX(2px)}'
       '.kl-otp:focus-visible{outline:2px solid #f2b544;outline-offset:3px}'
       '@media(prefers-reduced-motion:reduce){.kl-otp-a{transition:none}.kl-otp:hover .kl-otp-a{transform:none}}'
       '</style>' % MARK)

_LINE = ('<img src="%s" width="480" height="126" alt="OTP Bank" translate="no" decoding="async">'
         '<span data-uk="%s" data-ru="%s" data-ka="%s">%s</span><span class="kl-otp-a" aria-hidden="true">'
         '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14m-5-5 5 5-5 5"/></svg></span>'
         % (LOGO, TEXT['uk'], TEXT['ru'], TEXT['ka'], TEXT['uk']))

SCRIPT = ('<script id="%s-js">(function(){"use strict";var body=document.getElementById("kl-card-body");'
          'if(!body||!window.MutationObserver)return;var PAGE=%s,LINE=%s;'
          'function add(){var price=body.querySelector(".kl-body>.kl-tbd,.kl-body>.kl-usd");'
          'if(!price||body.querySelector(".kl-otp"))return;var a=document.createElement("a");a.className="kl-otp";'
          'a.href=document.documentElement.lang==="ru"?PAGE.ru:PAGE.uk;a.innerHTML=LINE;price.after(a);}'
          'new MutationObserver(add).observe(body,{childList:true});add();})();</script>'
          % (MARK, json.dumps(PAGE), json.dumps(_LINE, ensure_ascii=False).replace('</', '<\\/')))  # no </ inside the script

for _value in TEXT.values():
    if any(c in _value for c in '<>"&'):
        raise ValueError('LOT_OTP_TEXT')
