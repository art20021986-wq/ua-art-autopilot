"""Korea page lot card: every photo of the lot (KOREA-ENGINE-001, owner 2026-11-13).

The lot list (lots.json) keeps the first photos of each lot; when a card opens, its gallery file
(/video/korea/gallery/<id>.json, written by korea_auction.job.publish_galleries) adds the remaining photos after them,
so the swipe position stays. No file or an error: the card keeps the list's photos. Every other byte of
video/korea.html stays; each edit must match exactly once.
"""
OPEN = 'function open(id){'
SHOWN = '$("kl-card").showModal();$("kl-card").scrollTop=0;'
EDITS = (
    (OPEN,
     'function gallery(l){fetch("/video/korea/gallery/"+encodeURIComponent(l.id)+".json").then(function(r){'
     'return r.ok?r.json():null;}).then(function(g){var box=document.querySelector("#kl-card-body .kl-photos");'
     'if(!g||!g.photos||!box||!$("kl-card").open||location.hash!=="#lot-"+l.id)return;'
     'box.insertAdjacentHTML("beforeend",g.photos.slice(box.children.length).map(function(p){'
     'return \'<img alt="" loading="lazy" decoding="async" src="\'+esc(p)+\'">\';}).join(""));})'
     '.catch(function(){});}' + OPEN),
    (SHOWN, SHOWN + 'gallery(l);'),
)
# Public proof that this release is live.
CHECK = 'function gallery(l){'


def build(source):
    text = source.decode('utf-8')
    if CHECK in text or any(text.count(old) != 1 for old, _ in EDITS):
        raise ValueError('GALLERY_ANCHOR')
    for old, new in EDITS:
        text = text.replace(old, new)
    return text.encode('utf-8')
