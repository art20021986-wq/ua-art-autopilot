"""Korea lot window viewer styles: the catalogue gallery styles (ua_media_styles, byte for byte) and the few rules
for the lot window — the photo frame, a large high-contrast counter and arrows (owner 2026-11-13: «крупно,
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
    '.kg-gallery .um-prev,.kg-gallery .um-next{min-width:52px;min-height:52px;font-size:34px!important;'
    'border-color:#fff;background:rgba(8,13,20,.9)}'
)
CSS = CATALOGUE + LOT
