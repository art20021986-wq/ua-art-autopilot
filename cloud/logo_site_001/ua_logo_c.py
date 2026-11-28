"""The new logo C in the site headers (LOGO-001, owner «Да» 2026-11-28; cloud/logo_001/c_badge.svg).

CSS only: the «UA» square in both header kinds (a.brand .brand-mark; .shapka .logo .znak) shows the shield «UA» + «ART»
in its own box instead of the gold square with the letters; the letters stay in the markup (links and screen readers are
unchanged) but are not drawn. No ring: the shield has its own gold border. The company name next to it stays centred on
the logo's middle line. ua_brand_home puts CSS into its <head> block on every page.
"""
import base64

SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><linearGradient id="g" '
    'gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="120" y2="120"><stop offset="0" stop-color="#F1D27A"/>'
    '<stop offset="1" stop-color="#B8862B"/></linearGradient></defs>\n'
    '<path d="M60 6 L108 22 V58 Q108 96 60 114 Q12 96 12 58 V22 Z" fill="#0B1524" stroke="url(#g)" stroke-width="5" '
    'stroke-linejoin="round"/>\n'
    '<g transform="translate(1 -4)">\n'
    '<path d="M34 36 V62 Q34 78 48 78 Q57 78 60 70 L70 36 L84 78" fill="none" stroke="url(#g)" stroke-width="9" '
    'stroke-linecap="round" stroke-linejoin="round"/>\n'
    '<path d="M65 64 H79" stroke="url(#g)" stroke-width="7" stroke-linecap="round"/>\n'
    '</g>\n'
    '<text x="30.5" y="93" textLength="59" lengthAdjust="spacing" font-family="Inter Display" font-weight="800" '
    'font-size="13" fill="#F1D27A">ART</text>\n'
    '</svg>\n'
)
URI = 'data:image/svg+xml;base64,' + base64.b64encode(SVG.encode('utf-8')).decode('ascii')
CSS = (
    'a.brand .brand-mark,.shapka .logo .znak{background:url(' + URI + ') center/contain no-repeat!important;'
    'color:transparent!important;font-size:0!important;border:0!important;outline:0!important;box-shadow:none!important;'
    'border-radius:0!important;text-shadow:none!important}'
    'a.brand,.shapka .logo{display:flex!important;align-items:center!important}'
)
