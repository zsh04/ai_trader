# Strategy-agnostic policy shell. Plug signal model outputs here.
def should_enter(signal_prob: float, min_prob: float = 0.55) -> bool:
    return signal_prob >= min_prob
