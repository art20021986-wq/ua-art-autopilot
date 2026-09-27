"""Correct gallery frame sizing and upgrade saved card URLs without other edits."""
import ast
from pathlib import Path
from media_migration import upgrade_card as migrate_html
from previous_media_styles import CSS as PREVIOUS_CSS
from ua_media_styles import CSS
from ua_media_gallery import MARKER

ASSET_NAMES = ('ua_media_gallery.py', 'ua_media_script.py', 'ua_media_styles.py')
SOURCE_NAMES = ('stranica.py', *ASSET_NAMES)
MODULES = ()
LEGACY = "\nvar sloj=document.getElementById('lupa'),bol=document.getElementById('bolshoe'),\n    sch=document.getElementById('lupaschet');\nfunction pokazat(i){tek=(i+kadry.length)%kadry.length;bol.src=kadry[tek];\n sloj.style.display='flex';sch.style.display='block';sch.textContent=(tek+1)+' / '+kadry.length;\n document.body.style.overflow='hidden';}\nfunction zakryt(){sloj.style.display='none';sch.style.display='none';document.body.style.overflow='';}\ndocument.querySelectorAll('.lenta img').forEach(function(el,i){\n el.addEventListener('click',function(){pokazat(i);});});\nvar x0=null;\nsloj.addEventListener('touchstart',function(e){x0=e.touches[0].clientX;});\nsloj.addEventListener('touchend',function(e){if(x0===null)return;\n var dx=e.changedTouches[0].clientX-x0;\n if(Math.abs(dx)>50){pokazat(dx<0?tek+1:tek-1);}else{zakryt();}x0=null;});\nsloj.addEventListener('click',function(e){if(e.target===sloj)zakryt();});\n"

def build(sources):
    if set(sources) != set(SOURCE_NAMES):
        raise ValueError('FINAL_MEDIA_SOURCE_SET')
    for name in ASSET_NAMES:
        expected = 'previous_media_styles.py' if name == 'ua_media_styles.py' else name
        if sources[name] != Path(__file__).with_name(expected).read_bytes():
            raise ValueError('INSTALLED_MEDIA_ASSET_MISMATCH:'+name)
    tree = ast.parse(sources['stranica.py'])
    renderers = [node for node in tree.body if isinstance(node,ast.FunctionDef)
                 and node.name=='sobrat_kartochku'
                 and any(isinstance(child,ast.ImportFrom) and child.module=='ua_media_gallery'
                         for child in ast.walk(node))]
    if len(renderers) != 1:
        raise ValueError('MEDIA_RENDERER_NOT_INSTALLED')
    return {'ua_media_styles.py': Path(__file__).with_name('ua_media_styles.py').read_bytes()}

def upgrade_card(source):
    marker = '<!--'+MARKER+'-->'
    if marker not in source:
        return migrate_html(source, LEGACY)
    if source.count(marker) != 1:
        raise ValueError('MEDIA_ASSET_MARKER_DRIFT')
    before, after = '<style>'+PREVIOUS_CSS+'</style>', '<style>'+CSS+'</style>'
    if source.count(after) == 1 and before not in source:
        return source
    if source.count(before) != 1 or after in source:
        raise ValueError('MEDIA_STYLE_DRIFT')
    return source.replace(before, after, 1)
