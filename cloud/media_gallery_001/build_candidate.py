"""Patch only the original photo, video and viewer rendering blocks."""
import ast
from pathlib import Path

from media_migration import upgrade_card as migrate_html

SOURCE_NAMES = ('stranica.py',)
MODULES = ('ua_media_styles.py', 'ua_media_script.py', 'ua_media_gallery.py')

LEGACY = r'''
var sloj=document.getElementById('lupa'),bol=document.getElementById('bolshoe'),
    sch=document.getElementById('lupaschet');
function pokazat(i){tek=(i+kadry.length)%kadry.length;bol.src=kadry[tek];
 sloj.style.display='flex';sch.style.display='block';sch.textContent=(tek+1)+' / '+kadry.length;
 document.body.style.overflow='hidden';}
function zakryt(){sloj.style.display='none';sch.style.display='none';document.body.style.overflow='';}
document.querySelectorAll('.lenta img').forEach(function(el,i){
 el.addEventListener('click',function(){pokazat(i);});});
var x0=null;
sloj.addEventListener('touchstart',function(e){x0=e.touches[0].clientX;});
sloj.addEventListener('touchend',function(e){if(x0===null)return;
 var dx=e.changedTouches[0].clientX-x0;
 if(Math.abs(dx)>50){pokazat(dx<0?tek+1:tek-1);}else{zakryt();}x0=null;});
sloj.addEventListener('click',function(e){if(e.target===sloj)zakryt();});
'''


def constants(node):
    return [child.value for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)]


def patch_source(source):
    functions = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name == 'sobrat_kartochku'
                 and any("<div class='lenta'>" == value for value in constants(node))]
    if len(functions) != 1:
        raise ValueError('MEDIA_FUNCTION_ANCHOR')
    function = functions[0]
    photos = [node for node in function.body if isinstance(node, ast.If)
              and isinstance(node.test, ast.Name) and node.test.id == 'kadry'
              and "<div class='lenta'>" in constants(node)]
    videos = [node for node in function.body if isinstance(node, ast.If)
              and isinstance(node.test, ast.Name) and node.test.id == 'video_est']
    viewers = [node for node in function.body if isinstance(node, ast.If)
               and isinstance(node.test, ast.Name) and node.test.id == 'kadry'
               and (LEGACY in constants(node) or any(isinstance(c,ast.ImportFrom)
                    and c.module == 'ua_gallery' for c in ast.walk(node)))]
    if len(photos) != 1 or len(videos) != 1 or len(viewers) != 1:
        raise ValueError('MEDIA_RENDER_BLOCKS')
    photo, video, viewer = photos[0], videos[0], viewers[0]
    if photo.orelse or video.orelse or viewer.orelse:
        raise ValueError('MEDIA_UNEXPECTED_BRANCH')
    if len(photo.body) != 4 or not isinstance(photo.body[1],ast.For):
        raise ValueError('MEDIA_PHOTO_BLOCK_DRIFT')
    if LEGACY in constants(viewer):
        if len(viewer.body) != 4:
            raise ValueError('MEDIA_LEGACY_BLOCK_DRIFT')
    elif len(viewer.body) != 2:
        raise ValueError('MEDIA_DESKTOP_BLOCK_DRIFT')
    headings = [node for node in video.body if "<div class='zagolovok'>Видео</div>" in constants(node)]
    if len(headings) != 1 or len(video.body) != 8:
        raise ValueError('MEDIA_VIDEO_BLOCK_DRIFT')
    heading = headings[0]
    lines = source.splitlines(keepends=True)
    replacements = [
        (function.lineno,function.lineno, '    from ua_media_gallery import photos, videos, poster_url, assets\n'),
        (photo.lineno-1,photo.end_lineno, '    if kadry:\n        c.append(photos(kadry, sredn, nazvanie))\n'),
        (heading.end_lineno,video.end_lineno,
         '        c.append(videos(_vse, [poster_url(zastavka(_f) or poster) for _f in _vse], nazvanie))\n'),
        (viewer.lineno-1,viewer.end_lineno,'    c.append(assets())\n'),
    ]
    for begin,end,value in sorted(replacements,reverse=True):
        lines[begin:end] = [value]
    result = ''.join(lines)
    compile(result, 'stranica.py', 'exec')
    return result


def upgrade_card(source):
    return migrate_html(source, LEGACY)


def build(sources):
    if set(sources) != set(SOURCE_NAMES):
        raise ValueError('MEDIA_SOURCE_SET')
    result = {'stranica.py': patch_source(sources['stranica.py'].decode('utf-8')).encode('utf-8')}
    result.update({name: Path(__file__).with_name(name).read_bytes() for name in MODULES})
    return result
