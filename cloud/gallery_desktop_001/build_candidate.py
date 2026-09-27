"""Replace the exact legacy viewer block; all other source/HTML stays unchanged."""
import ast
import json
from pathlib import Path
import re

from ua_gallery import MARKER, render_viewer

SOURCE_NAMES = ('stranica.py',)
MODULES = ('ua_gallery.py',)
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


def patch_source(source):
    """Target the original car-card function, leaving diagnostics and wrappers intact."""
    functions = [node for node in ast.parse(source).body
                 if isinstance(node, ast.FunctionDef) and node.name == 'sobrat_kartochku'
                 and any(isinstance(child, ast.Constant) and child.value == LEGACY
                         for child in ast.walk(node))]
    if len(functions) != 1:
        raise ValueError('GALLERY_FUNCTION_ANCHOR')
    function = functions[0]
    blocks = [node for node in function.body if isinstance(node, ast.If)
              and isinstance(node.test, ast.Name) and node.test.id == 'kadry'
              and any(isinstance(child, ast.Constant) and child.value == LEGACY
                      for child in ast.walk(node))]
    if len(blocks) != 1 or blocks[0].orelse:
        raise ValueError('GALLERY_BLOCK_ANCHOR')
    block = blocks[0]
    if len(block.body) != 4:
        raise ValueError('GALLERY_STATEMENT_COUNT')
    lines = source.splitlines(keepends=True)
    replacement = ('    if kadry:\n'
                   '        from ua_gallery import render_viewer\n'
                   '        c.append(render_viewer(kadry))\n')
    result = ''.join(lines[:block.lineno-1]) + replacement + ''.join(lines[block.end_lineno:])
    compile(result, 'stranica.py', 'exec')
    return result


def upgrade_card(source):
    if '<!--' + MARKER + '-->' in source:
        return source
    start = "<div id='lupa'><img id='bolshoe' src='' alt=''></div><div id='lupaschet'></div>"
    if source.count(start) != 1:
        raise ValueError('GALLERY_HTML_ANCHOR')
    begin = source.index(start)
    end = source.find('</script>', begin)
    if end < 0:
        raise ValueError('GALLERY_SCRIPT_END')
    end += len('</script>')
    original = source[begin:end]
    match = re.fullmatch(re.escape(start) + r'<script>var kadry=(\[.*?\]);var tek=0;' +
                         re.escape(LEGACY) + r'</script>', original, re.S)
    if not match:
        raise ValueError('GALLERY_SCRIPT_DRIFT')
    urls = json.loads(match.group(1))
    return source[:begin] + render_viewer(urls) + source[end:]


def build(sources):
    if set(sources) != set(SOURCE_NAMES):
        raise ValueError('GALLERY_SOURCE_SET')
    return {'stranica.py': patch_source(sources['stranica.py'].decode('utf-8')).encode('utf-8'),
            'ua_gallery.py': Path(__file__).with_name('ua_gallery.py').read_bytes()}
