"""Korea page lot search: with «all makes» the «Model» list is grouped by make (KOREA-ENGINE-001, owner 2026-11-13).

Each make is an <optgroup> heading with its models under it, short («Sonata» under «Hyundai»); the option value stays the
full title, so the filter is unchanged. With one make chosen the list is as before. Every other byte stays.
"""
OLD = ('function models(){var m=$("kl-maker").value;opt($("kl-model"),uniq(lots.filter(function(l){'
       'return !m||l.maker===m;}).map(function(l){return l.title;})));}')
NEW = ('function models(){var m=$("kl-maker").value,s=$("kl-model"),keep=s.value,by={};'
       'lots.forEach(function(l){if(!m||l.maker===m)(by[l.maker]=by[l.maker]||[]).push(l.title);});'
       'if(m){opt(s,uniq(by[m]||[]));return;}opt(s,[]);'
       'Object.keys(by).sort().forEach(function(mk){var g=document.createElement("optgroup");g.label=mk;'
       'uniq(by[mk]).forEach(function(ti){var o=document.createElement("option");o.value=ti;'
       'o.textContent=ti.indexOf(mk+" ")===0?ti.slice(mk.length+1):ti;g.appendChild(o);});s.appendChild(g);});'
       's.value=keep;if(s.selectedIndex<0)s.value="";}')
# Public proof that this release is live.
CHECK = 'createElement("optgroup")'


def build(source):
    text = source.decode('utf-8')
    if CHECK in text or text.count(OLD) != 1:
        raise ValueError('MODEL_GROUPS_ANCHOR')
    return text.replace(OLD, NEW).encode('utf-8')
