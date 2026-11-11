"""Fresh AUTO.RIA figures in the home reviews block (AUTORIA-SOLD-001, owner 2026-11-11).

The weekly server job (cloud/autoria_sold_001) writes /video/brand/autoria-sold.json,
{"years": "5+", "sold": N, "reviews": N, ...}; this script puts each figure into its element. A figure that is missing
or not well formed (and everything while the file is missing or unreadable) keeps the value written in the page.
"""
SOURCE = '/video/brand/autoria-sold.json'
ID = 'ua-autoria-%s'  # % the figure's name in the file
FIELDS = ('years', 'sold', 'reviews')

SCRIPT = ("<script>fetch('%s',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null;})"
          ".then(function(d){if(!d)return;"
          "var ok={years:/^[1-9][0-9]?\\+?$/,sold:/^[1-9][0-9]{0,5}$/,reviews:/^[1-9][0-9]{0,5}$/};"
          "Object.keys(ok).forEach(function(k){var n=document.getElementById('%s'+k),v=d[k];"
          "if(n&&(typeof v==='number'||typeof v==='string')&&ok[k].test(String(v)))n.textContent=v;});})"
          ".catch(function(){});</script>"
          % (SOURCE, ID % ''))
