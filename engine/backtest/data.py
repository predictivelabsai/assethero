"""Alpaca market-data acquisition for the backtest methodology.

Per the skill, bars drive signal logic. We fetch daily (or intraday) bars from Alpaca
through the official `alpaca-py` SDK — the platform's first-class Alpaca client, not a
direct-HTTP bypass — then save the raw response and a normalized CSV, and compute a
per-symbol data fingerprint so runs are reproducible and reusable.

Normalized bar columns (skill canonical fields): t, o, h, l, c, v.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd


# alpaca-py feeds: 'iex' is available on free/paper data plans; 'sip' needs a subscription.
DEFAULT_FEED = os.getenv("ALPACA_DATA_FEED", "iex")
DEFAULT_ADJUSTMENT = "split"
ACCESS_METHOD = "alpaca-py"


@dataclass
class SymbolData:
    symbol: str
    bars: pd.DataFrame                      # normalized: index=ts(UTC), cols t,o,h,l,c,v
    raw_path: Path
    normalized_path: Path
    fingerprint: Dict = field(default_factory=dict)


def _paper_keys() -> tuple[str, str]:
    key = os.getenv("ALPACA_PAPER_API_KEY") or os.getenv("ALPACA_API_KEY") or ""
    sec = os.getenv("ALPACA_PAPER_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY") or ""
    if not key or not sec:
        raise RuntimeError(
            "Alpaca data requires ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY in the "
            "environment (.env). None found."
        )
    return key, sec


def _timeframe(interval: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    interval = interval.lower()
    table = {
        "1d": TimeFrame.Day,
        "1day": TimeFrame.Day,
        "1h": TimeFrame.Hour,
        "1hour": TimeFrame.Hour,
        "1min": TimeFrame(1, TimeFrameUnit.Minute),
        "5min": TimeFrame(5, TimeFrameUnit.Minute),
        "15min": TimeFrame(15, TimeFrameUnit.Minute),
    }
    if interval not in table:
        raise ValueError(f"Unsupported interval {interval!r}; use one of {sorted(table)}")
    return table[interval]


def _file_hash(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def fetch_symbol(
    symbol: str,
    start: datetime,
    end: datetime,
    raw_dir: Path,
    normalized_dir: Path,
    interval: str = "1d",
    feed: str = DEFAULT_FEED,
    adjustment: str = DEFAULT_ADJUSTMENT,
) -> SymbolData:
    """Fetch bars for one symbol, persist raw + normalized, and fingerprint."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.enums import Adjustment, DataFeed

    key, sec = _paper_keys()
    client = StockHistoricalDataClient(key, sec)
    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=_timeframe(interval),
        start=start,
        end=end,
        feed=DataFeed(feed),
        adjustment=Adjustment(adjustment),
    )
    barset = client.get_stock_bars(req)
    rows = [b.model_dump() for b in barset.data.get(symbol, [])]

    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"bars_{symbol}.json"
    raw_path.write_text(json.dumps(rows, default=str, indent=2))

    if rows:
        df = pd.DataFrame(rows)
        df["t"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.rename(columns={"open": "o", "high": "h", "low": "l", "close": "c", "volume": "v"})
        df = df[["t", "o", "h", "l", "c", "v"]].sort_values("t").reset_index(drop=True)
        df = df.set_index("t")
    else:
        df = pd.DataFrame(columns=["o", "h", "l", "c", "v"])
        df.index.name = "t"

    normalized_path = normalized_dir / f"bars_{symbol}.csv"
    df.to_csv(normalized_path)

    fingerprint = {
        "provider": "alpaca",
        "access_method": ACCESS_METHOD,
        "feed": feed,
        "adjustment": adjustment,
        "timeframe": interval,
        "extended_hours": False,
        "total_bars_fetched": int(len(df)),
        "bars_after_filter": int(len(df)),
        "first_bar_ts": (df.index[0].isoformat() if len(df) else None),
        "last_bar_ts": (df.index[-1].isoformat() if len(df) else None),
        "close_sum": (round(float(df["c"].sum()), 6) if len(df) else 0.0),
        "volume_sum": (float(df["v"].sum()) if len(df) else 0.0),
        "calendar_filter": "regular_hours_daily",
        "raw_file_hash": _file_hash(raw_path),
        "normalized_file_hash": _file_hash(normalized_path),
    }
    return SymbolData(symbol, df, raw_path, normalized_path, fingerprint)


def load_normalized(normalized_dir: Path, symbol: str) -> pd.DataFrame:
    """Re-load a normalized bar CSV (used by the in-folder run.py for reproducibility)."""
    path = normalized_dir / f"bars_{symbol}.csv"
    df = pd.read_csv(path, parse_dates=["t"]).set_index("t")
    return df
