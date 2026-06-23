"""Performance metrics per the skill (reference.md#metric-formulas).

Computed from a DAILY equity curve (not per-bar returns). Sharpe uses sample
standard deviation (N-1). These definitions are deliberately exact because the
skill guardrails forbid silently substituting variants.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def equity_metrics(equity: pd.Series) -> Dict[str, float]:
    """Total/annualized return, Sharpe (N-1, annualized), and max drawdown."""
    equity = equity.dropna().astype(float)
    if len(equity) < 2:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "final_equity": float(equity.iloc[-1]) if len(equity) else 0.0,
            "trading_days": int(len(equity)),
        }

    initial = float(equity.iloc[0])
    final = float(equity.iloc[-1])
    total_return = (final / initial) - 1 if initial else 0.0

    trading_days = len(equity)
    ann_return = (1 + total_return) ** (TRADING_DAYS / trading_days) - 1 if trading_days else 0.0

    daily = equity.pct_change().dropna()
    sd = daily.std(ddof=1)  # sample stddev, N-1
    sharpe = (daily.mean() / sd) * np.sqrt(TRADING_DAYS) if sd and sd > 0 else 0.0

    running_max = equity.cummax()
    drawdown = (equity / running_max) - 1
    max_drawdown = float(drawdown.min())

    return {
        "total_return": float(total_return),
        "annualized_return": float(ann_return),
        "sharpe": float(sharpe),
        "max_drawdown": max_drawdown,
        "final_equity": final,
        "trading_days": int(trading_days),
    }


def round_trip_metrics(round_trips: List[dict]) -> Dict[str, float]:
    """Trade count, hit rate, profit factor, fees — from realized round trips."""
    n = len(round_trips)
    if n == 0:
        return {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "fees_paid": 0.0,
                "wins": 0, "losses": 0}
    pnls = [float(rt["pnl"]) for rt in round_trips]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = len(wins) / n
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss == 0:
        profit_factor = float("inf") if gross_win > 0 else 0.0
    else:
        profit_factor = gross_win / gross_loss
    fees_paid = sum(float(rt.get("fees", 0.0)) for rt in round_trips)
    return {
        "trades": n,
        "win_rate": float(win_rate),
        "profit_factor": float(profit_factor),
        "fees_paid": float(fees_paid),
        "wins": len(wins),
        "losses": len(losses),
    }


def teaching_five(strat: Dict[str, float], bench: Dict[str, float], rt: Dict[str, float]) -> Dict:
    """The in-chat headline metrics: return vs benchmark, max dd, trades, win rate, Sharpe vs benchmark."""
    return {
        "total_return": strat["total_return"],
        "benchmark_total_return": bench["total_return"],
        "max_drawdown": strat["max_drawdown"],
        "trades": rt["trades"],
        "win_rate": rt["win_rate"],
        "sharpe": strat["sharpe"],
        "benchmark_sharpe": bench["sharpe"],
    }
