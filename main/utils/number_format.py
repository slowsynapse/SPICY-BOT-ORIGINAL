from math import log10, floor


def round_sig(x, sig=24):
    return round(x, sig-int(floor(log10(abs(x))))-1)
