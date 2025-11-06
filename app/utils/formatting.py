# app/utils/formatting.py
def fmt_money(x) -> str:
    try:
        return f"${float(x):,.2f}"
    except Exception:
        return "—"
