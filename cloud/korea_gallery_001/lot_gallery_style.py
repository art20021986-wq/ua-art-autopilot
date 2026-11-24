"""Korea lot window viewer styles: the catalogue gallery styles (ua_media_styles, byte for byte) and the few rules
for the lot window — the photo frame, a large high-contrast counter, small arrows (owner 2026-11-13: «крупно,
контрастно, понятный счётчик»), room for the window's own close button; the full-screen view uses the
catalogue's .um-dialog rules."""
from ua_media_styles import CSS as CATALOGUE

LOT = (
    '.kg-gallery{margin:0}'
    '.kg-gallery .um-view{border-radius:0}'
    '.kg-gallery .um-toolbar{padding-right:56px}'
    '.kg-gallery .um-counter{font:700 18px/1.3 system-ui,sans-serif;color:#fff}'
    '.kg-frame{width:100%;height:100%;touch-action:pan-y pinch-zoom;cursor:zoom-in}'
    '.kg-gallery .um-dialog .kg-frame{cursor:default}'
    '.kg-gallery .um-dialog .um-toolbar{padding-right:8px}'
    '.kg-frame img{display:block;width:100%;height:100%;object-fit:contain;user-select:none;-webkit-user-drag:none}'
    # small arrows (owner 2026-11-13): a 32 px visible plate and icon, the touch target stays 44 x 44 px (WCAG 2.5.5)
    '.kg-gallery .um-prev,.kg-gallery .um-next{width:44px;height:44px;min-width:44px;min-height:44px;padding:0;border:0;'
    'background:transparent;font-size:22px!important;line-height:1;isolation:isolate}'
    '.kg-gallery .um-prev::before,.kg-gallery .um-next::before{content:"";position:absolute;inset:6px;z-index:-1;'
    'border-radius:50%;border:1.5px solid #fff;background:rgba(8,13,20,.8)}'
)
CSS = CATALOGUE + LOT
