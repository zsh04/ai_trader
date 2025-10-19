from pydantic import BaseModel
import os, yaml, pathlib

class RiskConfig(BaseModel):
    max_risk_per_trade: float
    daily_drawdown_halt: float
    concentration_manual_gate: float
    max_notional_pct_adv: float

class SessionsConfig(BaseModel):
    pre: str
    reg_am: str
    reg_mid: str
    reg_pm: str
    aft: str

class WatchlistConfig(BaseModel):
    price_min: float
    price_max: float
    gap_min_pct: float
    rvol_min: float
    spread_max_pct_pre: float
    dollar_vol_min_pre: int
    max_watchlist: int

class ExecutionConfig(BaseModel):
    slippage_budget_pct: dict
    extended_hours_limit_only: bool

class Settings(BaseModel):
    timezone: str
    sessions: SessionsConfig
    watchlist: WatchlistConfig
    risk: RiskConfig
    execution: ExecutionConfig

def load_settings(path: str = "config/config.yaml") -> Settings:
    p = pathlib.Path(path)
    data = yaml.safe_load(p.read_text())
    return Settings(**data)
