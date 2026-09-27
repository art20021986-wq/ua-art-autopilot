"""Accessible photo controls shared by existing and newly rendered car cards.

No network access, dependencies, global event interception, or media changes.
"""
import json

MARKER = 'ua-gallery-desktop-v1'
CSS = r'''
.ua-gallery-shell{position:relative}
.ua-gallery-shell .lenta{cursor:grab}
.ua-gallery-shell .lenta.ua-gallery-dragging{cursor:grabbing;scroll-snap-type:none!important}
.ua-gallery-shell .lenta img{-webkit-user-drag:none;user-select:none}
.ua-gallery-button{position:absolute;z-index:3;top:50%;transform:translateY(-50%);width:48px;height:48px;border:1px solid #d2a44b;border-radius:50%;background:rgba(10,18,30,.92);color:#fff;font:32px/1 system-ui;cursor:pointer;display:grid;place-items:center;padding:0}
.ua-gallery-button:focus-visible,.ua-gallery-shell .lenta:focus-visible{outline:3px solid #f0a63c;outline-offset:3px}
.ua-gallery-prev{left:12px}.ua-gallery-next{right:12px}
.ua-gallery-button:disabled{display:none}
dialog#lupa{border:0;padding:0;margin:0;width:100vw;max-width:none;height:100vh;height:100dvh;max-height:none;inset:0;background:#000;color:#fff;overflow:hidden;touch-action:pan-y pinch-zoom}
dialog#lupa[open]{display:flex;align-items:center;justify-content:center}
dialog#lupa::backdrop{background:#000}
dialog#lupa #bolshoe{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;-webkit-user-drag:none;user-select:none}
dialog#lupa .ua-gallery-button{z-index:4}
dialog#lupa .ua-gallery-close{top:12px;right:12px;transform:none;font-size:28px}
dialog#lupa #lupaschet{position:absolute;display:block;top:18px;left:76px;right:76px;z-index:3;text-align:center;pointer-events:none;color:#fff;text-shadow:0 1px 4px #000;font:15px/1.5 system-ui}
'''

JS = r'''
(function (sources) {
  'use strict';
  const dialog = document.getElementById('lupa');
  const image = document.getElementById('bolshoe');
  const counter = document.getElementById('lupaschet');
  const rail = Array.from(document.querySelectorAll('.lenta')).find(el => el.querySelector('img'));
  if (!dialog || !image || !counter || !rail || !sources.length || !dialog.showModal) return;
  const photos = Array.from(rail.querySelectorAll('img'));
  if (photos.length !== sources.length) return;
  const frames = photos.map(el => el.parentElement);
  const words = {
    ru: ['Предыдущее фото', 'Следующее фото', 'Закрыть фотографии', 'Фотографии автомобиля'],
    uk: ['Попереднє фото', 'Наступне фото', 'Закрити фотографії', 'Фотографії автомобіля'],
    ka: ['წინა ფოტო', 'შემდეგი ფოტო', 'ფოტოების დახურვა', 'ავტომობილის ფოტოები']
  };
  const shell = document.createElement('div');
  shell.className = 'ua-gallery-shell';
  rail.before(shell);
  shell.append(rail);
  rail.tabIndex = 0;
  rail.style.scrollBehavior = 'auto';
  rail.setAttribute('role', 'group');
  rail.setAttribute('aria-roledescription', 'carousel');
  let active = 0;
  let opener = rail;
  let overflow = '';
  const wrap = value => (value + sources.length) % sources.length;
  function button(parent, className, symbol, action) {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'ua-gallery-button ' + className;
    el.textContent = symbol;
    el.addEventListener('click', action);
    parent.append(el);
    return el;
  }
  function nearest() {
    const start = frames[0].offsetLeft;
    let best = 0;
    frames.forEach((frame, index) => {
      if (Math.abs(frame.offsetLeft - start - rail.scrollLeft) <
          Math.abs(frames[best].offsetLeft - start - rail.scrollLeft)) best = index;
    });
    return best;
  }
  function select(index) {
    const target = frames[wrap(index)];
    rail.scrollTo({left: target.offsetLeft - frames[0].offsetLeft, behavior: 'auto'});
  }
  function show(index) {
    active = wrap(index);
    image.src = sources[active];
    image.alt = photos[active].alt;
    counter.textContent = (active + 1) + ' / ' + sources.length;
  }
  function open(index) {
    if (dialog.open) return;
    opener = document.activeElement;
    overflow = document.body.style.overflow;
    label();
    show(index);
    dialog.showModal();
    document.body.style.overflow = 'hidden';
    close.focus();
  }
  const previous = button(shell, 'ua-gallery-prev', '‹', () => select(nearest() - 1));
  const next = button(shell, 'ua-gallery-next', '›', () => select(nearest() + 1));
  const back = button(dialog, 'ua-gallery-prev', '‹', () => show(active - 1));
  const forward = button(dialog, 'ua-gallery-next', '›', () => show(active + 1));
  const close = button(dialog, 'ua-gallery-close', '×', () => dialog.close());
  function label() {
    const selected = document.querySelector('.ua-site-lang [aria-pressed="true"]');
    const locale = selected ? selected.getAttribute('data-lang') : document.documentElement.lang;
    const labels = words[locale] || words.ru;
    [previous, back].forEach(el => el.setAttribute('aria-label', labels[0]));
    [next, forward].forEach(el => el.setAttribute('aria-label', labels[1]));
    close.setAttribute('aria-label', labels[2]);
    rail.setAttribute('aria-label', labels[3]);
    dialog.setAttribute('aria-label', labels[3]);
  }
  label();
  const language = document.querySelector('.ua-site-lang');
  if (language) new MutationObserver(label).observe(language, {subtree: true, attributes: true, attributeFilter: ['aria-pressed']});
  [previous, next, back, forward].forEach(el => { el.disabled = sources.length < 2; });
  photos.forEach((photo, index) => {
    photo.draggable = false;
    photo.addEventListener('click', () => open(index));
  });
  image.draggable = false;
  dialog.addEventListener('close', () => {
    document.body.style.overflow = overflow;
    image.removeAttribute('src');
    if (opener && opener.isConnected && opener !== document.body) opener.focus({preventScroll: true});
    else rail.focus({preventScroll: true});
  });
  dialog.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault();
      show(active + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  rail.addEventListener('keydown', event => {
    if (event.target !== rail || event.altKey || event.ctrlKey || event.metaKey) return;
    const key = event.key;
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End', 'Enter', ' '].includes(key)) return;
    event.preventDefault();
    if (key === 'Enter' || key === ' ') open(nearest());
    else select(key === 'Home' ? 0 : key === 'End' ? sources.length - 1 : nearest() + (key === 'ArrowRight' ? 1 : -1));
  });
  // The photo rail keeps native touch/trackpad scrolling. Only mouse drag is added.
  let drag = null;
  let suppressRailClick = false;
  rail.addEventListener('dragstart', event => event.preventDefault());
  rail.addEventListener('pointerdown', event => {
    suppressRailClick = false;
    if (event.pointerType !== 'mouse' || event.button !== 0 || !event.isPrimary) return;
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY, start: rail.scrollLeft, index: nearest(), dx: 0, moved: false};
  });
  rail.addEventListener('pointermove', event => {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.x;
    drag.dx = dx;
    if (!drag.moved && Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(event.clientY - drag.y)) {
      drag.moved = true;
      rail.setPointerCapture(event.pointerId);
      rail.classList.add('ua-gallery-dragging');
    }
    if (drag.moved) {
      event.preventDefault();
      rail.scrollLeft = drag.start - dx;
    }
  });
  function endDrag(event) {
    if (!drag || drag.id !== event.pointerId) return;
    const moved = drag.moved;
    let index = nearest();
    if (moved && event.type === 'pointerup' && index === drag.index && Math.abs(drag.dx) > 50) index += drag.dx < 0 ? 1 : -1;
    drag = null;
    rail.classList.remove('ua-gallery-dragging');
    if (rail.hasPointerCapture(event.pointerId)) rail.releasePointerCapture(event.pointerId);
    if (moved) {
      suppressRailClick = true;
      select(index);
    }
  }
  rail.addEventListener('pointerup', endDrag);
  rail.addEventListener('pointercancel', endDrag);
  rail.addEventListener('lostpointercapture', endDrag);
  rail.addEventListener('click', event => {
    if (!suppressRailClick) return;
    suppressRailClick = false;
    event.preventDefault();
    event.stopImmediatePropagation();
  }, true);
  let swipe = null;
  let suppressDialogClick = false;
  let dialogPressTarget = null;
  dialog.addEventListener('pointerdown', event => {
    suppressDialogClick = false;
    if (!event.isPrimary || event.button !== 0 || event.target.closest('button')) return;
    dialogPressTarget = event.target;
    swipe = {id: event.pointerId, x: event.clientX, y: event.clientY};
    dialog.setPointerCapture(event.pointerId);
  });
  dialog.addEventListener('pointerup', event => {
    if (!swipe || swipe.id !== event.pointerId) return;
    const dx = event.clientX - swipe.x;
    const dy = event.clientY - swipe.y;
    swipe = null;
    if (dialog.hasPointerCapture(event.pointerId)) dialog.releasePointerCapture(event.pointerId);
    if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) {
      suppressDialogClick = true;
      show(active + (dx < 0 ? 1 : -1));
    }
  });
  dialog.addEventListener('pointercancel', () => { swipe = null; });
  dialog.addEventListener('click', event => {
    if (suppressDialogClick) { suppressDialogClick = false; return; }
    if (event.target === dialog && dialogPressTarget === dialog) dialog.close();
  });
})(__UA_GALLERY_SOURCES__);
'''


def render_viewer(sources):
    """Render only gallery controls, using the renderer's original ordered URLs."""
    values = list(sources)
    if not values:
        return ''
    if not all(isinstance(value, str) and value for value in values):
        raise ValueError('GALLERY_SOURCE_URL')
    encoded = json.dumps(values, ensure_ascii=True).replace('<', '\\u003c')
    return ('<!--' + MARKER + '--><style>' + CSS + '</style>'
            '<dialog id="lupa"><img id="bolshoe" alt="">'
            '<div id="lupaschet" role="status" aria-live="polite" aria-atomic="true"></div></dialog>'
            '<script>' + JS.replace('__UA_GALLERY_SOURCES__', encoded) + '</script>')
