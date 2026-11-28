"""Google tag (GA4) for public pages: the snippet and its idempotent insertion; no I/O.

Leads sent to Analytics: «generate_lead» when the order form is saved or handed off to Telegram,
«contact» on a phone, Telegram, Viber or WhatsApp link (parameter «method»).
"""
import re

MEASUREMENT_ID = 'G-6SRBQK6GY4'
MARK = '<!--UA-GTAG-V1-->'
END = '<!--/UA-GTAG-V1-->'
HEAD = re.compile(r'<head(?:\s[^>]*)?>', re.I)

EVENTS = r"""(function(){var last={};
function lead(name,method){var key=name+'|'+method,now=Date.now();if(last[key]&&now-last[key]<2000)return;last[key]=now;gtag('event',name,{method:method});}
function contact(href){var h=href.toLowerCase();if(h.indexOf('tel:')===0)return 'phone';if(h.indexOf('viber:')===0)return 'viber';
if(/^tg:|\/\/(t\.me|telegram\.me)\//.test(h))return 'telegram';if(/\/\/(wa\.me|api\.whatsapp\.com)\/|^whatsapp:/.test(h))return 'whatsapp';return '';}
document.addEventListener('click',function(e){var t=e.target;if(!t||!t.closest)return;
if(t.closest('#ua-order #handoff')){lead('generate_lead','order_telegram');return;}
var a=t.closest('a[href]');var m=a?contact(a.getAttribute('href')):'';if(m)lead('contact',m);},true);
document.addEventListener('DOMContentLoaded',function(){var r=document.querySelector('#ua-order #receipt');if(!r||!window.MutationObserver)return;
new MutationObserver(function(){if(r.hidden)return;try{if(sessionStorage.getItem('ua_gtag_lead'))return;sessionStorage.setItem('ua_gtag_lead','1');}catch(x){}
lead('generate_lead','order_form');}).observe(r,{attributes:true,attributeFilter:['hidden']});});})();"""

SNIPPET = (MARK + '<script async src="https://www.googletagmanager.com/gtag/js?id=' + MEASUREMENT_ID + '"></script>'
           '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
           "gtag('js',new Date());gtag('config','" + MEASUREMENT_ID + "');\n" + EVENTS + '</script>' + END)


def apply(html):
    """The page with the tag right after <head>; unchanged if already tagged or without a head."""
    if not isinstance(html, str) or MARK in html:
        return html
    head = HEAD.search(html)
    if not head:
        return html
    return html[:head.end()] + SNIPPET + html[head.end():]
