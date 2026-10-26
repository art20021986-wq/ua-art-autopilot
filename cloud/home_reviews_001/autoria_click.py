"""Google Analytics event for clicks on the AUTO.RIA links of the home page (AUTORIA-REVIEWS-001).

Owner request 2026-10-26: count visits to the dealer page. One delegated listener sends the custom event
«autoria_click» with «placement» (reviews block or footer badge) through the site's existing gtag; without
gtag nothing happens. The links open a new tab, so the page stays and the hit is not cut off.
"""
ATTRIBUTE = 'data-autoria'
BLOCK = 'reviews_block'
BADGE = 'footer_badge'
EVENT = 'autoria_click'

SCRIPT = ("<script>document.addEventListener('click',function(e){var a=e.target&&e.target.closest&&"
          "e.target.closest('a[%s]');if(a&&typeof gtag==='function')gtag('event','%s',{placement:a.getAttribute('%s')});});"
          "</script>" % (ATTRIBUTE, EVENT, ATTRIBUTE))
