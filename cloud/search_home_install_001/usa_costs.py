"""Fixed parts of the USA turnkey price (SEARCH-HOME-001, owner 2026-11-26). One place to change a number.

The shipping part (auction yard -> Poti) comes from the weekly tariff file; everything else is here.
"""
BUY_FEE = ((1, 200), (5, 100), (10, 0))  # cars bought at once -> fee per car, $ (partner fee x2, owner 26.11)
PORT_GEORGIA = 400                         # port costs in Georgia per car, $
TRUCK_GEORGIA_KYIV = 1100                  # car carrier Georgia -> Kyiv per car, $
SERVICE = 600                              # UA ART service under the contract, $
EXPENSIVE_FROM = 15000                     # cars from this price: +1% insurance (partner's Standard terms)


def buy_fee(cars=1):
    fee = BUY_FEE[0][1]
    for start, value in BUY_FEE:
        if cars >= start:
            fee = value
    return fee


def public():
    """The numbers the page's script needs (written into tariffs.json next to the yards)."""
    return {'buy': buy_fee(1), 'port': PORT_GEORGIA, 'truck': TRUCK_GEORGIA_KYIV, 'service': SERVICE,
            'expensive_from': EXPENSIVE_FROM}
