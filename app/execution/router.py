# Order router presets
def bracket_for_entry(entry_px: float, atr: float, tp_mult=1.5, sl_mult=1.0):
    tp = entry_px + tp_mult * atr
    sl = entry_px - sl_mult * atr
    return tp, sl
