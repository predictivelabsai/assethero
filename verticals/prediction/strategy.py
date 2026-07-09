"""Weather-edge trading strategy for prediction markets (Polymarket).

Pure-Python: no network, no heavy deps — safe to import anywhere. Ports the
polytrade weather methodology:

  * `parse_threshold`     — pull the temperature bucket (°F/°C) out of a market
                            question like "Highest temperature in NYC on July 9?".
  * `fair_probability`    — heuristic fair YES price from observed/forecast weather.
  * `resolve_outcome`     — resolution-aware payout (did the day's high land in the
                            bucket?), used by the backtester.
  * `WeatherEdgeStrategy` — edge / confidence / BUY-SELL-HOLD-SKIP signal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class TradeSignal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    SKIP = "SKIP"


@dataclass
class TradeOpportunity:
    market_id: str
    city: str
    market_question: str
    market_price: float
    fair_price: float
    edge_percentage: float
    signal: TradeSignal
    confidence: float
    liquidity: float
    reasoning: str


# --- weather → fair-value helpers ------------------------------------------

def parse_threshold(question: str) -> Dict[str, Any]:
    """Extract a temperature threshold (always returned in °F) from a question."""
    # Ranges first, e.g. "14-15°F" / "between 10 and 20".
    range_match = re.search(r"(\d+(?:\.\d+)?)\s*[-to]\s*(\d+(?:\.\d+)?)", question)
    if range_match:
        val1 = float(range_match.group(1))
        val2 = float(range_match.group(2))
        unit_match = re.search(r"[0-9]\s*°?([CF])", question, re.IGNORECASE)
        unit = unit_match.group(1).upper() if unit_match else "F"
        avg_val = (val1 + val2) / 2
        if unit == "C":
            return {"value": (avg_val * 9 / 5) + 32, "unit": "F", "original_unit": "C"}
        return {"value": avg_val, "unit": "F"}

    match = re.search(r"(-?\d+(?:\.\d+)?)\s*°?([CF])", question, re.IGNORECASE)
    if not match:
        match = re.search(r"(-?\d+(?:\.\d+)?)", question)
        if not match:
            return {"value": -999.0, "unit": "F"}
        return {"value": float(match.group(1)), "unit": "F"}

    val = float(match.group(1))
    unit = match.group(2).upper()
    if unit == "C":
        return {"value": (val * 9 / 5) + 32, "unit": "F", "original": val, "original_unit": "C"}
    return {"value": val, "unit": "F"}


def _classify(question: str):
    q = question.lower()
    is_above = "or higher" in q or "exceed" in q or "above" in q
    is_below = "or below" in q or "below" in q or "less than" in q
    return is_above, is_below, not (is_above or is_below)


def fair_probability(actual_tempmax_f: float, question: str) -> float:
    """Heuristic fair YES price given the day's (observed or forecast) high."""
    target = parse_threshold(question).get("value", 0.0)
    diff = actual_tempmax_f - target
    is_above, is_below, is_discrete = _classify(question)

    if is_discrete:
        ad = abs(diff)
        if ad < 0.5:
            prob = 0.90
        elif ad < 1.0:
            prob = 0.70
        elif ad < 1.5:
            prob = 0.30
        elif ad < 2.0:
            prob = 0.10
        else:
            prob = 0.02
    elif is_below:
        if diff < -1.5:
            prob = 0.98
        elif diff > 1.5:
            prob = 0.02
        else:
            prob = 0.5 - (diff / 2.5)
    else:  # is_above
        if diff > 1.5:
            prob = 0.98
        elif diff < -1.5:
            prob = 0.02
        else:
            prob = 0.5 + (diff / 2.5)

    return max(0.01, min(0.99, prob))


def resolve_outcome(actual_tempmax_f: float, question: str) -> float:
    """Resolution-aware YES payout: 1.0 if the day's high satisfied the bucket."""
    target = parse_threshold(question).get("value", 0.0)
    is_above, is_below, is_discrete = _classify(question)
    if is_discrete:
        return 1.0 if abs(actual_tempmax_f - target) < 1.1 else 0.0
    if is_below:
        return 1.0 if actual_tempmax_f <= (target + 0.1) else 0.0
    return 1.0 if actual_tempmax_f >= (target - 0.1) else 0.0


# --- signal engine ----------------------------------------------------------

class WeatherEdgeStrategy:
    """Edge / confidence / signal for a single market vs its weather fair value."""

    def __init__(self, min_liquidity: float = 50.0, min_edge: float = 0.15,
                 max_price: float = 0.10, min_confidence: float = 0.60):
        self.min_liquidity = min_liquidity
        self.min_edge = min_edge
        self.max_price = max_price
        self.min_confidence = min_confidence

    def analyze_market(self, market_id: str, city: str, market_question: str,
                       market_price: float, fair_price: float,
                       liquidity: float) -> TradeOpportunity:
        if market_price <= 0:
            return TradeOpportunity(market_id, city, market_question, market_price,
                                    fair_price, 0.0, TradeSignal.SKIP, 0.0,
                                    liquidity, "Invalid market price")
        edge = (fair_price - market_price) / market_price
        confidence = self._confidence(edge, market_price, liquidity, fair_price)
        signal = self._signal(edge, market_price, liquidity, confidence)
        reasoning = (f"Signal {signal.value} | mkt ${market_price:.3f} | "
                     f"fair ${fair_price:.3f} | edge {edge*100:+.1f}% | "
                     f"conf {confidence:.0%} | liq ${liquidity:.0f}")
        return TradeOpportunity(market_id, city, market_question, market_price,
                                fair_price, edge, signal, confidence, liquidity, reasoning)

    def _confidence(self, edge, price, liquidity, fair):
        c = 0.5
        c += min(abs(edge) / 0.5, 1.0) * 0.3
        c += min(liquidity / 500.0, 1.0) * 0.2
        if 0.05 <= price <= 0.95:
            c += 0.1
        elif 0.01 <= price <= 0.99:
            c += 0.05
        if 0.1 <= fair <= 0.9:
            c += 0.1
        return min(c, 1.0)

    def _signal(self, edge, price, liquidity, confidence):
        if liquidity < self.min_liquidity:
            return TradeSignal.SKIP
        if price > self.max_price:
            return TradeSignal.SKIP
        if confidence < self.min_confidence:
            return TradeSignal.HOLD
        if edge >= self.min_edge:
            return TradeSignal.BUY
        if edge <= -self.min_edge:
            return TradeSignal.SELL
        return TradeSignal.HOLD
