"""Korea logistics prices in step 3 (owner 2026-11-11): defaults written in the page, monthly prices from the CRM bot.

The CRM bot («💲 Цены Корея», a later package) writes SOURCE:
    {"version": 1, "months": {"2026-11": {"fob": 600, "container": 4800, "port": 250, "truck": 1100,
                                         "broker": 150, "cert": 150}, "2026-12": {...}}}
The script takes the latest month not after today's (so prices for the coming months can be entered in advance) and
fills the numbers and the month; per car the container counts as container / CARS_PER_CONTAINER. While the file is
missing, unreadable or incomplete, the numbers written in the page stay.
"""
SOURCE = '/video/korea/logistics.json'
KEYS = ('fob', 'container', 'port', 'truck', 'broker', 'cert')
DEFAULTS = {'fob': 600, 'container': 4800, 'port': 250, 'truck': 1100, 'broker': 150, 'cert': 150}
MONTH = '2026-11'
CARS_PER_CONTAINER = 4
ATTR = 'data-ua-kr'  # data-ua-kr="fob" … "total", "car_container", "month"


def per_car(prices):
    return prices['container'] // CARS_PER_CONTAINER


def total(prices):
    return sum(prices[k] for k in KEYS if k != 'container') + per_car(prices)


def money(value):
    """3450 -> '3 450' (no-break space), as the site writes prices."""
    return '{:,}'.format(value).replace(',', ' ')


def month(value):
    """'2026-11' -> '11.2026' (the same in every language)."""
    year, number = value.split('-')
    return '%s.%s' % (number, year)


def initial(key):
    """The number written in the page for key."""
    if key == 'total':
        return money(total(DEFAULTS))
    if key == 'car_container':
        return money(per_car(DEFAULTS))
    if key == 'month':
        return month(MONTH)
    return money(DEFAULTS[key])


SCRIPT = ("<script>(function(){fetch('%(src)s',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null;})"
          ".then(function(d){if(!d||d.version!==1||!d.months)return;"
          "var now=new Date(),cur=now.getFullYear()+'-'+('0'+(now.getMonth()+1)).slice(-2),m=null;"
          "Object.keys(d.months).forEach(function(k){if(/^\\d{4}-\\d{2}$/.test(k)&&k<=cur&&(!m||k>m))m=k;});"
          "var p=m&&d.months[m],keys=%(keys)s;"
          "if(!p||!keys.every(function(k){return Number.isInteger(p[k])&&p[k]>=0;}))return;"
          "var f=function(n){return String(n).replace(/\\B(?=(\\d{3})+(?!\\d))/g,'\\u00a0');},"
          "car=Math.floor(p.container/%(per)d),v={total:car,car_container:car,month:m.slice(5)+'.'+m.slice(0,4)};"
          "keys.forEach(function(k){v[k]=p[k];if(k!=='container')v.total+=p[k];});"
          "document.querySelectorAll('[%(attr)s]').forEach(function(n){var k=n.getAttribute('%(attr)s');"
          "if(k in v)n.textContent=k==='month'?v[k]:f(v[k]);});}).catch(function(){});})();</script>"
          % {'src': SOURCE, 'keys': '[%s]' % ','.join("'%s'" % k for k in KEYS), 'per': CARS_PER_CONTAINER,
             'attr': ATTR})
