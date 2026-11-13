"""KOREA-WEEK-DAYS-001 (owner 2026-11-12): the day buttons of the korea.html lot list always show 7 days — today and
the next 6 days (Korea time, UTC+9, no summer time) — each with its number of cars; a day without listed lots shows 0.

The auction site lists lots only for its next one or two auction days, so the page took its days from the lots alone
(KOREA-LOTS-FULL-001: only 2 buttons). Now the buttons come from the calendar; a listed day later than the week keeps
its button after the 7. One exact edit of the live page (the fragment must occur exactly once; a page that already
has the edit is refused); every other byte stays.
"""
PAGE = 'video/korea.html'
OLD = 'var ks=Object.keys(c).sort();'
NEW = 'var ks=week(c);'
# week(c) -> ['YYYY/MM/DD' x 7 from today in Korea] + listed days after them; c = cars per day.
WEEK = ('function week(c){var k=Date.now()+324e5,r=[];for(var i=0;i<7;i++)'
        'r.push(new Date(k+i*864e5).toISOString().slice(0,10).replace(/-/g,"/"));'
        'return r.concat(Object.keys(c).filter(function(d){return d>r[6];}).sort());}')
ANCHOR = 'function days(){'
CHECK = 'function week(c){'


def build(text):
    """The live korea.html (text) with the 7-day buttons."""
    if CHECK in text:
        raise ValueError('KOREA_WEEK_DAYS_ALREADY_APPLIED')
    for fragment in (OLD, ANCHOR):
        if text.count(fragment) != 1:
            raise ValueError('KOREA_WEEK_DAYS_FRAGMENT_NOT_UNIQUE:' + fragment)
    return text.replace(OLD, NEW).replace(ANCHOR, WEEK + ANCHOR)
