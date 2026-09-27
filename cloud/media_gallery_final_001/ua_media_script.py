"""Native browser interactions; one selection state and one player per gallery."""
JS = r'''
(() => {
  'use strict';
  const words = {
    ru: ['Фото','Видео','Назад','Вперёд','Увеличить','На весь экран','Закрыть','Загрузка…','Не удалось загрузить файл','Повторить','Фотографии автомобиля','Видео автомобиля','Полноэкранный режим недоступен. Открыт увеличенный просмотр.'],
    uk: ['Фото','Відео','Назад','Далі','Збільшити','На весь екран','Закрити','Завантаження…','Не вдалося завантажити файл','Повторити','Фотографії автомобіля','Відео автомобіля','Повноекранний режим недоступний. Відкрито збільшений перегляд.'],
    ka: ['ფოტო','ვიდეო','წინა','შემდეგი','გადიდება','სრულ ეკრანზე','დახურვა','იტვირთება…','ფაილი ვერ ჩაიტვირთა','ხელახლა ცდა','ავტომობილის ფოტოები','ავტომობილის ვიდეო','სრული ეკრანი მიუწვდომელია. გახსნილია გადიდებული ხედი.']
  };
  const instances = [];
  function locale() {
    const selected = document.querySelector('.ua-site-lang [aria-pressed="true"]');
    return words[(selected && selected.getAttribute('data-lang')) || document.documentElement.lang] || words.ru;
  }
  document.querySelectorAll('[data-ua-media]').forEach(root => {
    if (root.dataset.ready) return;
    const data = JSON.parse(root.querySelector('.um-data').textContent);
    if (!data.length) return;
    root.dataset.ready = 'true';
    const photo = root.dataset.uaMedia === 'photo';
    const q = selector => root.querySelector(selector);
    const mount = q('.um-mount'), view = q('.um-view'), dialog = q('.um-dialog');
    const panel = q('.um-panel'), rail = q('.um-thumbs'), counter = q('.um-counter');
    const previous = q('.um-prev'), next = q('.um-next'), close = q('.um-close');
    const expand = q('.um-expand'), full = q('.um-fullscreen');
    const state = q('.um-state'), retry = q('.um-retry'), message = q('.um-message');
    const tabs = Array.from(rail.querySelectorAll('[role="tab"]'));
    let active = 0, opener = null, overflow = '', player = q('video');
    let loadState = '', gesture = null, dragged = false;
    const positions = new Map();
    const bounded = index => Math.max(0, Math.min(data.length - 1, index));
    const noun = () => locale()[photo ? 0 : 1];
    function stateOf(value) {
      loadState = value;
      state.hidden = !value;
      state.querySelector('span').textContent = locale()[value === 'error' ? 8 : 7];
      retry.hidden = value !== 'error';
      panel.setAttribute('aria-busy', String(value === 'loading'));
    }
    function label() {
      const w = locale();
      [[previous,2],[next,3],[expand,4],[full,5],[close,6],[retry,9]].forEach(([el,i]) => el.setAttribute('aria-label',w[i]));
      retry.textContent = w[9];
      const title = w[photo ? 10 : 11];
      root.setAttribute('aria-label',title); dialog.setAttribute('aria-label',title); rail.setAttribute('aria-label',title);
      tabs.forEach((tab,i) => tab.setAttribute('aria-label',noun()+' '+(i+1)+' / '+data.length));
      counter.textContent = noun()+' '+(active+1)+' / '+data.length;
      const button = q('.um-image-button');
      if (button) {button.setAttribute('aria-label',w[4]+' '+noun().toLowerCase()); button.querySelector('img').alt = data[active].alt+' — '+noun().toLowerCase()+' '+(active+1);}
      if (loadState) stateOf(loadState);
    }
    function showImage() {
      const item = data[active];
      const img = new Image();
      img.decoding = 'async'; img.draggable = false;
      img.alt = item.alt+' — '+noun().toLowerCase()+' '+(active+1);
      stateOf('loading');
      const button = q('.um-image-button');
      // Detached previous images cannot commit a stale load or error state.
      img.addEventListener('load', () => {if (button.firstElementChild === img) stateOf('');});
      img.addEventListener('error', () => {if (button.firstElementChild === img) stateOf('error');});
      button.replaceChildren(img);
      img.src = dialog.open ? item.src : item.preview;
    }
    function saveVideo() {
      if (player && Number.isFinite(player.currentTime)) positions.set(active, player.currentTime);
      if (player) player.pause();
    }
    function bindVideo(video, index) {
      video.addEventListener('loadedmetadata', () => {
        if (video !== player) return;
        const saved = positions.get(index) || 0;
        if (saved && Number.isFinite(video.duration)) video.currentTime = Math.min(saved, video.duration);
        stateOf('');
      });
      video.addEventListener('error', () => {if (video === player) stateOf('error');});
      video.addEventListener('play', () => instances.forEach(instance => {if (instance.root !== root) instance.pause();}));
    }
    function showVideo() {
      const old = player, item = data[active];
      const video = document.createElement('video');
      video.controls = true; video.playsInline = true; video.preload = 'none';
      if (item.preview) video.poster = item.preview;
      player = video;
      bindVideo(video, active);
      const link = document.createElement('a'); link.href = item.src; link.textContent = noun(); video.append(link);
      video.src = item.src;
      panel.replaceChildren(video);
      if (old) {old.removeAttribute('src'); old.load();}
      stateOf('');
    }
    function reveal(tab) {
      const left = tab.offsetLeft - rail.offsetLeft;
      if (left < rail.scrollLeft || left + tab.offsetWidth > rail.scrollLeft + rail.clientWidth)
        rail.scrollTo({left: left - (rail.clientWidth - tab.offsetWidth)/2, behavior:'auto'});
    }
    function select(index) {
      index = bounded(index);
      if (active === index) {
        tabs.forEach((tab,i) => {tab.tabIndex = i===active ? 0 : -1;});
        reveal(tabs[active]); return;
      }
      saveVideo(); active = index;
      tabs.forEach((tab,i) => {tab.setAttribute('aria-selected',String(i===active)); tab.tabIndex = i===active ? 0 : -1;});
      panel.setAttribute('aria-labelledby',tabs[active].id);
      previous.disabled = active === 0; next.disabled = active === data.length-1;
      photo ? showImage() : showVideo();
      label(); reveal(tabs[active]);
    }
    function open() {
      if (dialog.open) return;
      opener = document.activeElement; overflow = document.body.style.overflow;
      mount.style.minHeight = mount.getBoundingClientRect().height+'px';
      dialog.showModal(); dialog.append(view);
      document.body.style.overflow = 'hidden';
      expand.hidden = true; close.focus();
      if (photo) showImage();
      reveal(tabs[active]);
    }
    async function fullscreen() {
      open();
      try {
        if (document.fullscreenElement) {await document.exitFullscreen(); return;}
        if (view.requestFullscreen && document.fullscreenEnabled) await view.requestFullscreen();
        else if (player && player.webkitEnterFullscreen) player.webkitEnterFullscreen();
        else throw new Error('unsupported');
      } catch (_) {message.textContent = locale()[12]; message.hidden = false;}
    }
    function closeDialog() {
      if (document.fullscreenElement === view) document.exitFullscreen().catch(() => {});
      dialog.close();
    }
    expand.addEventListener('click', open); full.addEventListener('click', fullscreen);
    close.addEventListener('click', closeDialog);
    dialog.addEventListener('cancel', event => {event.preventDefault(); closeDialog();});
    dialog.addEventListener('close', () => {
      saveVideo(); mount.append(view); mount.style.minHeight = '';
      document.body.style.overflow = overflow; expand.hidden = false; message.hidden = true;
      if (photo) showImage();
      if (opener && opener.isConnected) opener.focus({preventScroll:true});
      else expand.focus({preventScroll:true});
      reveal(tabs[active]);
    });
    let backdropPress = false;
    dialog.addEventListener('pointerdown', e => {backdropPress = e.target === dialog;});
    dialog.addEventListener('click', e => {if (e.target === dialog && backdropPress) closeDialog();});
    previous.addEventListener('click', () => select(active-1)); next.addEventListener('click', () => select(active+1));
    retry.addEventListener('click', () => {if (photo) showImage(); else {showVideo(); player.preload='metadata'; player.load();}});
    rail.addEventListener('click', event => {
      if (dragged) {event.preventDefault(); dragged=false; return;}
      const tab = event.target.closest('[role="tab"]');
      if (tab) select(Number(tab.dataset.index));
    });
    rail.addEventListener('keydown', event => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const tab = event.target.closest('[role="tab"]');
      if (!tab) return;
      const i = Number(tab.dataset.index);
      const keys = {ArrowRight:(i+1)%tabs.length, ArrowLeft:(i-1+tabs.length)%tabs.length, Home:0, End:tabs.length-1};
      if (Object.hasOwn(keys,event.key)) {
        event.preventDefault(); event.stopPropagation();
        tabs.forEach((el,j) => {el.tabIndex = j===keys[event.key] ? 0 : -1;});
        tabs[keys[event.key]].focus({preventScroll:true}); reveal(tabs[keys[event.key]]);
      }
    });
    rail.addEventListener('focusout', event => {
      if (!rail.contains(event.relatedTarget)) tabs.forEach((tab,i) => {tab.tabIndex = i===active ? 0 : -1;});
    });
    view.addEventListener('keydown', event => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('video,.um-thumbs')) return;
      const target = {ArrowLeft:active-1, ArrowRight:active+1, Home:0, End:data.length-1};
      if (Object.hasOwn(target,event.key)) {event.preventDefault(); select(target[event.key]);}
    });
    // Native touch/trackpad scrolling, with mouse drag confined to the thumbnail rail.
    rail.addEventListener('dragstart', e => e.preventDefault());
    rail.addEventListener('pointerdown', e => {
      dragged=false;
      if (e.pointerType==='mouse' && e.button===0) gesture={id:e.pointerId,x:e.clientX,start:rail.scrollLeft};
    });
    rail.addEventListener('pointermove', e => {
      if (!gesture || e.pointerId!==gesture.id) return;
      const dx=e.clientX-gesture.x;
      if (Math.abs(dx)>6) {dragged=true; rail.classList.add('um-dragging'); rail.setPointerCapture(e.pointerId); rail.scrollLeft=gesture.start-dx;}
    });
    function endDrag(e) {gesture=null; rail.classList.remove('um-dragging'); if(rail.hasPointerCapture(e.pointerId)) rail.releasePointerCapture(e.pointerId);}
    rail.addEventListener('pointerup',endDrag); rail.addEventListener('pointercancel',endDrag);
    rail.addEventListener('lostpointercapture', () => {gesture=null; rail.classList.remove('um-dragging');});
    if (photo) {
      const button=q('.um-image-button'); let swipe=null, moved=false;
      button.addEventListener('pointerdown', e => {moved=false; if(e.isPrimary && e.button===0) swipe={id:e.pointerId,x:e.clientX,y:e.clientY};});
      button.addEventListener('pointerup', e => {
        if(!swipe || e.pointerId!==swipe.id) return;
        const dx=e.clientX-swipe.x,dy=e.clientY-swipe.y; swipe=null;
        if(Math.abs(dx)>50 && Math.abs(dx)>Math.abs(dy)){moved=true; select(active+(dx<0?1:-1));}
      });
      button.addEventListener('pointercancel', () => {swipe=null;});
      button.addEventListener('click', () => {if(moved){moved=false;return;} open();});
      const img=button.querySelector('img');
      img.addEventListener('error',()=>{if(button.firstElementChild===img)stateOf('error');});
      if(img.complete && !img.naturalWidth) stateOf('error');
    } else bindVideo(player, 0);
    root.querySelectorAll('.um-thumb img').forEach(img => {
      img.addEventListener('error', () => {img.hidden=true;});
      if (img.complete && !img.naturalWidth) img.hidden=true;
    });
    if (!dialog.showModal) {
      expand.hidden=true;full.hidden=true;
      const button=q('.um-image-button');
      if(button) button.disabled=true;
    }
    instances.push({root,pause:saveVideo,label}); label();
  });
  const language = document.querySelector('.ua-site-lang');
  if(language) new MutationObserver(() => instances.forEach(x=>x.label())).observe(language,{subtree:true,attributes:true,attributeFilter:['aria-pressed']});
  new MutationObserver(() => instances.forEach(x=>x.label())).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  document.addEventListener('visibilitychange', () => {if(document.hidden) instances.forEach(x=>x.pause());});
})();
'''
