from dataclasses import dataclass
from typing import List
import json, os, datetime, pathlib

@dataclass
class Candidate:
    symbol: str
    price: float
    gap_pct: float
    rvol: float
    spread_pct: float
    dollar_vol: float

def scan_premarket() -> List[Candidate]:
    # Placeholder: integrate Alpaca data client later
    # For now, produce a few fake candidates in $1-$10 with decent RVOL
    return [
        Candidate("ABC", 3.45, 8.2, 4.0, 0.4, 2_500_000),
        Candidate("XYZ", 9.10, 6.0, 3.2, 0.6, 1_200_000),
    ]

def write_watchlist(cands: List[Candidate], out_dir: str = "data/watchlists"):
    dt = datetime.datetime.now().strftime("%Y-%m-%d")
    pathlib.Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = pathlib.Path(out_dir) / f"{dt}.json"
    with open(path, "w") as f:
        json.dump([c.__dict__ for c in cands], f, indent=2)
    return str(path)
