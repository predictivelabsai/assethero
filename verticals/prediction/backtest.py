"""Resolution-aware weather backtester for Polymarket temperature markets.

Synchronous, pragmatic port of the polytrade BacktestEngine. For each day in the
lookback window (ending yesterday) it:

  1. discovers the "Highest temperature in <city> on <Month D>" market series via
     the broker's Gamma search, filtering by city/date/topic/year;
  2. pulls the day's weather high from the weather feed (Visual Crossing primary);
  3. scores each temperature bucket with `strategy.fair_probability` and reads the
     start-of-day entry price from CLOB price history;
  4. selects the best YES edge (plus a NO hedge in v2 mode);
  5. settles each selected trade against the actual outcome
     (`strategy.resolve_outcome`) at $100/trade and accumulates PnL.

Everything is injected (broker, weather feed) so this module has no import-time
network or heavy-dep requirements.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from verticals.prediction.strategy import (
    parse_threshold, fair_probability, resolve_outcome,
)

logger = logging.getLogger(__name__)

ALLOCATION_PER_TRADE = 100.0
CITY_ALIASES = {"NYC": "New York", "NYC.": "New York", "NEW YORK CITY": "New York",
                "LA": "Los Angeles", "L.A.": "Los Angeles"}


def _weather_city(city: str) -> str:
    return CITY_ALIASES.get(city.upper(), city)


def _filter_markets(markets, city: str, weather_city: str, date_str: str):
    d = datetime.strptime(date_str, "%Y-%m-%d")
    full = f"{d.strftime('%B')} {d.day}"       # "July 9"
    abbr = f"{d.strftime('%b')} {d.day}"       # "Jul 9"
    year = date_str[:4]
    terms = {city.lower(), weather_city.lower()}
    out = []
    seen = set()
    for m in markets:
        if m.id in seen:
            continue
        q = m.question.lower()
        if not any(t in q for t in terms):
            continue
        if full not in m.question and abbr not in m.question:
            continue
        if "highest temperature" not in q:
            continue
        m_year = (m.end_date[:4] if m.end_date and len(m.end_date) >= 4
                  else (m.created_at[:4] if m.created_at and len(m.created_at) >= 4 else None))
        if m_year and m_year != year:
            continue
        out.append(m)
        seen.add(m.id)
    return out


def run_backtest(broker, weather_feed, city: str, target_date: Optional[str] = None,
                 lookback_days: int = 7, v2_mode: bool = False,
                 strategy_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run the resolution-aware weather backtest. Returns a summary dict."""
    target_date = target_date or datetime.now().strftime("%Y-%m-%d")
    wcity = _weather_city(city)

    end_dt = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(days=1)
    count = max(1, lookback_days)
    date_range = [(end_dt - timedelta(days=i)).strftime("%Y-%m-%d")
                  for i in range(count - 1, -1, -1)]

    total_invested = total_payout = 0.0
    trades_summary: List[Dict[str, Any]] = []
    markets_found = 0

    for current_date in date_range:
        d = datetime.strptime(current_date, "%Y-%m-%d")
        queries = {
            f"Highest temperature in {city}",
            f"Highest temperature in {wcity}",
            f"{d.strftime('%B')} {d.day} {city} weather",
            f"{city} weather", wcity, city,
        }
        raw = []
        for q in queries:
            raw.extend(broker.gamma_search(q, status="all", limit=200))
        markets = _filter_markets(raw, city, wcity, current_date)
        if not markets:
            continue

        weather = weather_feed.get_day_weather(wcity, current_date)
        if not weather or weather.get("tempmax") is None:
            continue
        actual_high = float(weather.get("tempmax"))
        markets_found += len(markets)

        # Score each bucket at start-of-day.
        target_ts = int(datetime.strptime(f"{current_date} 00:00:00",
                                           "%Y-%m-%d %H:%M:%S").timestamp())
        group = []
        for m in markets:
            info = parse_threshold(m.question)
            if info.get("value") == -999:
                continue
            fair = fair_probability(actual_high, m.question)
            price = m.yes_price
            if m.clob_token_ids:
                history = broker.get_price_history(m.clob_token_ids[0])
                closest, best_diff = None, float("inf")
                for h in history:
                    hts = int(h.get("t", h.get("timestamp", 0)) or 0)
                    if abs(hts - target_ts) < best_diff:
                        best_diff, closest = abs(hts - target_ts), h
                if closest:
                    price = float(closest.get("p", closest.get("price", price)) or price)
            group.append({"market": m, "price": price, "fair": fair,
                          "edge": fair - price})

        if not group:
            continue

        # Select best YES (and best NO in v2).
        yes = sorted([g for g in group if g["price"] > 0 and g["edge"] > 0.02],
                     key=lambda x: x["edge"], reverse=True)
        no = sorted([g for g in group if g["price"] > 0 and g["edge"] < -0.02],
                    key=lambda x: -x["edge"], reverse=True)
        selected = []
        if yes:
            selected.append(("YES", yes[0]))
        if v2_mode and no and (not yes or no[0]["market"].id != yes[0]["market"].id):
            selected.append(("NO", no[0]))

        for side, g in selected:
            m = g["market"]
            entry = g["price"] if side == "YES" else (1.0 - g["price"])
            if entry <= 0:
                continue
            shares = ALLOCATION_PER_TRADE / entry
            yes_res = resolve_outcome(actual_high, m.question)
            outcome = yes_res if side == "YES" else (1.0 - yes_res)
            payout = shares * outcome
            pnl = payout - ALLOCATION_PER_TRADE
            total_invested += ALLOCATION_PER_TRADE
            total_payout += payout
            bucket = m.question.split(" be ")[-1].split(" on ")[0]
            trades_summary.append({
                "date": current_date, "market_id": m.id, "market_name": m.question,
                "bucket": bucket, "Side": side, "city": city,
                "target_f": round(parse_threshold(m.question).get("value", 0), 1),
                "actual_high": round(actual_high, 1),
                "price": round(entry, 3), "edge": round(abs(g["edge"]), 3),
                "result": f"WIN ({side})" if outcome > 0.9 else f"LOSS ({side})",
                "pnl": round(pnl, 2),
            })

    final_pnl = total_payout - total_invested
    final_roi = (final_pnl / total_invested * 100) if total_invested > 0 else 0.0
    return {
        "success": True,
        "city": city,
        "period": f"{date_range[0]} to {date_range[-1]}" if date_range else "",
        "lookback_days": lookback_days,
        "v2_mode": v2_mode,
        "total_invested": round(total_invested, 2),
        "total_payout": round(total_payout, 2),
        "final_pnl": round(final_pnl, 2),
        "final_roi": round(final_roi, 2),
        "markets_found": markets_found,
        "trades": trades_summary,
    }
