"""Google tag (GA4 and Google Ads) for public pages: the snippet and its idempotent insertion; no I/O.

Leads sent to Analytics: «generate_lead» when the order form is saved or handed off to Telegram,
«contact» on a phone, Telegram, Viber or WhatsApp link (parameter «method»).
Google Ads (ADS-AWTAG-001, V2): the same tag is configured for AW-18537441937, and every «generate_lead»
(the events below and quick-lead.js's own gtag call) also sends one Google Ads conversion. No user data is sent.
The block keeps the V1 markers: the catalogue design guard and the page checks leave it out by them.
"""
import re

MEASUREMENT_ID = 'G-6SRBQK6GY4'
ADS_ID = 'AW-18537441937'
ADS_SEND_TO = ADS_ID + '/fvkWCIT9vsAdEJHVq4dF'
MARK = '<!--UA-GTAG-V1-->'
END = '<!--/UA-GTAG-V1-->'
HEAD = re.compile(r'<head(?:\s[^>]*)?>', re.I)
BLOCK = re.compile(re.escape(MARK) + r'.*?' + re.escape(END), re.S)

# gtag is wrapped once: a «generate_lead» event, whoever sends it, is followed by one conversion to Google Ads.
ADS = ("gtag('config','" + ADS_ID + "');\n"
       "(function(){var base=gtag;gtag=function(){base.apply(this,arguments);"
       "if(arguments[0]==='event'&&arguments[1]==='generate_lead')base('event','conversion',{send_to:'"
       + ADS_SEND_TO + "'});};})();\n")

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
           "gtag('js',new Date());gtag('config','" + MEASUREMENT_ID + "');\n" + ADS + EVENTS + '</script>' + END)


def apply(html):
    """The page with the tag right after <head>; an earlier tag block is replaced by this one; unchanged if the page
    already has it, has no head, or has an unexpected number of tag blocks."""
    if not isinstance(html, str):
        return html
    if MARK in html:
        found = BLOCK.findall(html)
        if len(found) != 1 or html.count(MARK) != 1 or found[0] == SNIPPET:
            return html
        return html.replace(found[0], SNIPPET, 1)
    head = HEAD.search(html)
    if not head:
        return html
    return html[:head.end()] + SNIPPET + html[head.end():]
