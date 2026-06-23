"""Named fill models, position sizing, and execution friction.

Implements the skill's Fill model rules (reference.md#fill-model-rules):

- next_open (default): signal on bar t close, fill at bar t+1 open.
- time_based: fill at a confirmed timestamp (not used for the daily Phase-0 path).
- same_bar: explicit request only; the runner forces a look-ahead warning into the report.

Friction (bar-based fallback, no quotes):
    buy  = price * (1 + friction_pct)
    sell = price * (1 - friction_pct)
    friction_pct = (spread_bps + slippage_bps) / 10000

Sizing is computed at signal time (bar t close), floored to whole shares unless
fractional is requested.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import floor

FILL_MODELS = ("next_open", "time_based", "same_bar")
DEFAULT_FILL_MODEL = "next_open"


@dataclass(frozen=True)
class Friction:
    spread_bps: float = 0.0
    slippage_bps: float = 5.0

    @property
    def pct(self) -> float:
        return (self.spread_bps + self.slippage_bps) / 10000.0

    def buy(self, price: float) -> float:
        return price * (1 + self.pct)

    def sell(self, price: float) -> float:
        return price * (1 - self.pct)


def size_shares(cash: float, fraction: float, signal_close: float, fractional: bool = False) -> float:
    """Shares to buy: fraction of available cash at the signal-bar close price."""
    if signal_close <= 0:
        return 0.0
    raw = (cash * fraction) / signal_close
    return float(raw) if fractional else float(floor(raw))


def fill_price_for_bar(model: str, side: str, bar: dict, friction: Friction) -> float:
    """Return the friction-adjusted fill price for a market order under a fill model.

    `bar` is the bar at the fill timestamp (for next_open: bar t+1; for same_bar: bar t).
    Field used: open for next_open/time_based, close for same_bar.
    """
    base = bar["o"] if model in ("next_open", "time_based") else bar["c"]
    return friction.buy(base) if side == "buy" else friction.sell(base)


def stop_fill(side: str, stop_level: float, bar: dict, friction: Friction) -> float | None:
    """Conservative stop fill on a bar (skill stop rules). Returns fill price or None."""
    if side == "sell":  # protective stop on a long
        if bar["l"] <= stop_level:
            return friction.sell(min(bar["o"], stop_level))
    else:  # buy stop
        if bar["h"] >= stop_level:
            return friction.buy(max(bar["o"], stop_level))
    return None


def limit_fill(side: str, limit_price: float, bar: dict, friction: Friction) -> float | None:
    """Conservative limit fill on a bar (skill limit rules). Returns fill price or None."""
    if side == "sell":  # take-profit on a long
        if bar["h"] >= limit_price:
            return friction.sell(max(bar["o"], limit_price))
    else:  # buy limit
        if bar["l"] <= limit_price:
            return friction.buy(min(bar["o"], limit_price))
    return None
