"""Korea page: the lot window photo viewer (KOREA-GALLERY-001, owner 2026-11-13).

1. The page script's own photo loader (KOREA-ENGINE-001 gallery(l)) is removed: the viewer loads the lot's photos.
2. The viewer block (styles + script, lot_gallery_style / lot_gallery_script) goes before </body>.
Every other byte of video/korea.html stays; each edit must match exactly once.
"""
import re

import lot_gallery_script
import lot_gallery_style

MARK = 'UA-KOREA-GALLERY-V1'
LOADER = ('function gallery(l){fetch("/video/korea/gallery/"+encodeURIComponent(l.id)+".json").then(function(r){'
          'return r.ok?r.json():null;}).then(function(g){var box=document.querySelector("#kl-card-body .kl-photos");'
          'if(!g||!g.photos||!box||!$("kl-card").open||location.hash!=="#lot-"+l.id)return;'
          'box.insertAdjacentHTML("beforeend",g.photos.slice(box.children.length).map(function(p){'
          'return \'<img alt="" loading="lazy" decoding="async" src="\'+esc(p)+\'">\';}).join(""));})'
          '.catch(function(){});}')
CALL = 'scrollTop=0;gallery(l);'
BODY = re.compile(r'(?=</body\s*>)', re.I)
BLOCK = ('<!--%s--><style id="ua-korea-gallery-css">%s</style><script id="ua-korea-gallery-js">%s</script><!--/%s-->'
         % (MARK, lot_gallery_style.CSS, lot_gallery_script.JS, MARK))
# Public proof that this release is live.
CHECK = 'id="ua-korea-gallery-js"'


def build(source):
    text = source.decode('utf-8')
    if (MARK in text or text.count(LOADER) != 1 or text.count(CALL) != 1 or len(BODY.findall(text)) != 1
            or text.count('id="kl-card-body"') != 1):
        raise ValueError('KOREA_GALLERY_ANCHOR')
    text = text.replace(LOADER, '').replace(CALL, 'scrollTop=0;')
    return BODY.sub(lambda m: BLOCK, text, count=1).encode('utf-8')
