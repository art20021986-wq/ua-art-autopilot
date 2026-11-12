"""Korea page: the OTP credit line style before </head> and its script before </body> (LOT-OTP-001).

Every other byte of video/korea.html stays. The page must have its lot window and exactly one </head> and </body>, and
the release must not be live yet, otherwise nothing is changed.
"""
import re

import lot_otp

HEAD = re.compile(r'(?=</head\s*>)', re.I)
BODY = re.compile(r'(?=</body\s*>)', re.I)
WINDOW = 'id="kl-card-body"'
# Public proof that this release is live.
CHECK = 'id="%s-js"' % lot_otp.MARK


def build(source):
    text = source.decode('utf-8')
    if (lot_otp.MARK in text or text.count(WINDOW) != 1 or len(HEAD.findall(text)) != 1
            or len(BODY.findall(text)) != 1):
        raise ValueError('LOT_OTP_ANCHOR')
    text = HEAD.sub(lambda m: lot_otp.CSS, text, count=1)
    text = BODY.sub(lambda m: lot_otp.SCRIPT, text, count=1)
    return text.encode('utf-8')
