"""Styles scoped to the car media component, including its native dialog."""
CSS = r'''
.um-gallery{margin:16px 0;color:var(--tekst,#fff);min-width:0}
.um-gallery *{box-sizing:border-box}
.um-gallery [hidden]{display:none!important}
.um-view{width:100%;min-width:0;background:var(--karta,#142131);border-radius:14px;overflow:hidden}
.um-toolbar{display:flex;align-items:center;gap:8px;min-height:52px;padding:4px 8px}
.um-counter{margin-right:auto;font:14px/1.4 system-ui;color:inherit}
.um-gallery button{font:inherit;cursor:pointer;color:inherit}
.um-tool{min-width:44px;min-height:44px;border:1px solid #657285;border-radius:8px;background:#162331;color:#fff!important;padding:8px}
.um-tool:disabled{opacity:.35;cursor:default}
.um-stage{position:relative;aspect-ratio:4/3;max-height:70vh;min-height:150px;background:#080d14;display:grid;place-items:center;overflow:hidden}
.um-panel{position:relative;width:100%;height:100%;min-height:0;display:grid;place-items:center}
.um-image-button{display:block;border:0;padding:0;width:100%;height:100%;background:transparent;touch-action:pan-y pinch-zoom;cursor:zoom-in!important}
.um-image-button img,.um-panel video{display:block;width:100%;height:100%;max-height:100%;object-fit:contain}
.um-image-button img{user-select:none;-webkit-user-drag:none}
.um-dialog .um-image-button{cursor:default!important}
.um-prev,.um-next{position:absolute;z-index:2;top:50%;transform:translateY(-50%);font-size:28px!important;background:rgba(8,13,20,.82)}
.um-prev{left:8px}.um-next{right:8px}
.um-state{position:absolute;z-index:1;inset:0;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:12px;background:#080d14;color:#fff;text-align:center;padding:16px;pointer-events:none}
.um-state button{pointer-events:auto}
.um-thumbs{display:flex;gap:8px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x proximity;padding:10px;touch-action:pan-x pan-y;scrollbar-width:thin;cursor:grab}
.um-thumbs.um-dragging{cursor:grabbing;scroll-snap-type:none;user-select:none}
.um-thumb{position:relative;flex:0 0 92px;height:70px;padding:0;border:3px solid transparent;border-radius:8px;overflow:hidden;background:#243447;scroll-snap-align:center}
.um-thumb img{width:100%;height:100%;object-fit:cover;pointer-events:none;-webkit-user-drag:none}
.um-thumb[aria-selected=true]{border-color:var(--zoloto,#d2a44b)}
.um-number{position:absolute;bottom:3px;right:3px;font:12px/1.4 system-ui;background:rgba(0,0,0,.8);color:white;border-radius:3px;padding:0 4px}
.um-playmark{position:absolute;left:5px;top:5px;color:white;text-shadow:0 1px 4px black}
.um-gallery :focus-visible{outline:3px solid #f3ba58;outline-offset:2px}
.um-dialog{padding:0;border:0;margin:auto;background:transparent;color:#fff;width:min(1200px,96vw);max-width:100vw;max-height:96vh;max-height:96dvh;overflow:visible}
.um-dialog::backdrop{background:rgba(0,0,0,.92)}
.um-dialog .um-view{height:min(900px,94vh);height:min(900px,94dvh);display:grid;grid-template-rows:auto minmax(0,1fr) auto;background:#080d14}
.um-dialog .um-stage{aspect-ratio:auto;max-height:none;min-height:0}
.um-dialog .um-view:fullscreen{width:100%;height:100%;max-height:none;border-radius:0;background:#080d14}
.um-close{display:none}.um-dialog .um-close{display:block}
.um-message{font:13px/1.4 system-ui;padding:4px 10px;color:inherit}
@media(max-width:600px){.um-thumb{flex-basis:76px;height:58px}.um-dialog{width:100vw;max-height:100vh;max-height:100dvh}.um-dialog .um-view{height:100vh;height:100dvh;border-radius:0;padding-top:env(safe-area-inset-top);padding-bottom:env(safe-area-inset-bottom)}.um-toolbar{gap:4px}.um-tool{padding:6px}.um-stage{max-height:60vh}}
@media(prefers-reduced-motion:reduce){.um-gallery *{scroll-behavior:auto!important}}
'''
