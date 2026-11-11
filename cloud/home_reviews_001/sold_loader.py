"""Fresh AUTO.RIA sold-cars number in the home reviews block (AUTORIA-SOLD-001, owner 2026-11-11).

The weekly server job (cloud/autoria_sold_001) writes /video/brand/autoria-sold.json, {"sold": N, ...}; this
script puts N into the block. While the file is missing or unreadable the number written in the page stays.
"""
SOURCE = '/video/brand/autoria-sold.json'
ID = 'ua-autoria-sold'

SCRIPT = ("<script>fetch('%s',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null;})"
          ".then(function(d){var n=document.getElementById('%s');"
          "if(n&&d&&Number.isInteger(d.sold)&&d.sold>0)n.textContent=d.sold;}).catch(function(){});</script>"
          % (SOURCE, ID))
