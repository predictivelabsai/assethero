"""Paper trading + DB persistence for the prediction vertical.

Persists to the SHARED assethero tables — `runs`, `trades`, `backtest_summaries` —
tagging rows with ``vertical='prediction'`` and ``trade_type='paper'|'backtest'``.
There is NO real order placement here; a paper "buy" records an intended fill at the
current market YES price.

All DB access goes through `utils.db.db_pool.DatabasePool` (reads `DATABASE_URL` via
the pool) — no hardcoded DSN. Every DB import is lazy so this module imports without
SQLAlchemy or a live database.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VERTICAL = "prediction"
VENUE = "polymarket"


def _pool():
    from utils.db.db_pool import DatabasePool
    return DatabasePool()


# --- runs -------------------------------------------------------------------

def ensure_run(run_id: str, mode: str, user_id: Optional[str] = None,
               strategy: str = "weather-edge", config: Optional[dict] = None) -> str:
    """Idempotently create a prediction run row (vertical='prediction')."""
    import json
    from sqlalchemy import text
    with _pool().get_session() as s:
        s.execute(text("""
            INSERT INTO assethero.runs
                (run_id, user_id, vertical, venue, mode, strategy, status, config, started_at)
            VALUES
                (:run_id, :user_id, :vertical, :venue, :mode, :strategy, 'running', :config, :started_at)
            ON CONFLICT (run_id) DO NOTHING
        """), {
            "run_id": run_id, "user_id": user_id, "vertical": VERTICAL, "venue": VENUE,
            "mode": mode, "strategy": strategy,
            "config": json.dumps(config or {}, default=str),
            "started_at": datetime.now(timezone.utc),
        })
    return run_id


def complete_run(run_id: str, status: str = "completed",
                 results: Optional[dict] = None) -> None:
    import json
    from sqlalchemy import text
    with _pool().get_session() as s:
        s.execute(text("""
            UPDATE assethero.runs SET status = :status, results = :results,
                   completed_at = :ts WHERE run_id = :run_id
        """), {"run_id": run_id, "status": status,
               "results": json.dumps(results or {}, default=str),
               "ts": datetime.now(timezone.utc)})


def recent_runs(limit: int = 20, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    from sqlalchemy import text
    clause = "WHERE vertical = :vertical"
    params: Dict[str, Any] = {"vertical": VERTICAL, "limit": limit}
    if user_id:
        clause += " AND user_id = :user_id"
        params["user_id"] = user_id
    with _pool().get_session() as s:
        rows = s.execute(text(f"""
            SELECT run_id, mode, strategy, strategy_slug, status,
                   config, results, created_at
            FROM assethero.runs {clause}
            ORDER BY created_at DESC LIMIT :limit
        """), params).mappings().all()
    return [dict(r) for r in rows]


# --- paper trades -----------------------------------------------------------

def record_paper_trade(user_id: Optional[str], market_id: str, question: str,
                       side: str, amount: float, price: float,
                       city: Optional[str] = None) -> Dict[str, Any]:
    """Record a paper buy into assethero.trades (trade_type='paper')."""
    from sqlalchemy import text
    run_id = f"pred-paper-{user_id or 'cli'}"
    ensure_run(run_id, "paper", user_id=user_id)
    shares = amount / price if price > 0 else 0.0
    order_id = f"PP-{uuid.uuid4().hex[:12]}"
    with _pool().get_session() as s:
        s.execute(text("""
            INSERT INTO assethero.trades
                (run_id, user_id, trade_type, vertical, venue, symbol, direction,
                 shares, entry_time, entry_price, order_id, reason)
            VALUES
                (:run_id, :user_id, 'paper', :vertical, :venue, :symbol, :direction,
                 :shares, :entry_time, :entry_price, :order_id, :reason)
        """), {
            "run_id": run_id, "user_id": user_id, "vertical": VERTICAL, "venue": VENUE,
            "symbol": str(market_id)[:16], "direction": side[:8], "shares": shares,
            "entry_time": datetime.now(timezone.utc), "entry_price": price,
            "order_id": order_id, "reason": (question or "")[:500],
        })
    return {"order_id": order_id, "market_id": market_id, "side": side,
            "amount": amount, "price": price, "shares": shares, "city": city}


def close_paper_trade(user_id: Optional[str], order_id: str,
                      exit_price: float) -> Optional[Dict[str, Any]]:
    """Close an open paper position by order_id, booking realized PnL."""
    from sqlalchemy import text
    run_id = f"pred-paper-{user_id or 'cli'}"
    with _pool().get_session() as s:
        row = s.execute(text("""
            SELECT id, shares, entry_price FROM assethero.trades
            WHERE run_id = :run_id AND order_id LIKE :oid AND exit_time IS NULL
            LIMIT 1
        """), {"run_id": run_id, "oid": f"%{order_id}"}).mappings().first()
        if not row:
            return None
        shares = float(row["shares"] or 0)
        entry = float(row["entry_price"] or 0)
        pnl = shares * exit_price - shares * entry
        s.execute(text("""
            UPDATE assethero.trades
            SET exit_time = :ts, exit_price = :exit_price, pnl = :pnl
            WHERE id = :id
        """), {"ts": datetime.now(timezone.utc), "exit_price": exit_price,
               "pnl": pnl, "id": row["id"]})
    return {"order_id": order_id, "exit_price": exit_price, "pnl": pnl}


def fetch_paper_trades(user_id: Optional[str] = None,
                       limit: int = 100) -> List[Dict[str, Any]]:
    from sqlalchemy import text
    clause = "WHERE vertical = :vertical AND trade_type = 'paper'"
    params: Dict[str, Any] = {"vertical": VERTICAL, "limit": limit}
    if user_id:
        clause += " AND user_id = :user_id"
        params["user_id"] = user_id
    with _pool().get_session() as s:
        rows = s.execute(text(f"""
            SELECT order_id, symbol, direction, shares, entry_price, exit_price,
                   pnl, entry_time, exit_time, reason
            FROM assethero.trades {clause}
            ORDER BY entry_time DESC LIMIT :limit
        """), params).mappings().all()
    return [dict(r) for r in rows]


def portfolio_summary(user_id: Optional[str] = None) -> Dict[str, Any]:
    """Aggregate paper PnL for the prediction vertical."""
    trades = fetch_paper_trades(user_id=user_id, limit=1000)
    open_t = [t for t in trades if t.get("exit_time") is None]
    closed = [t for t in trades if t.get("exit_time") is not None]
    invested = sum(float(t["shares"] or 0) * float(t["entry_price"] or 0) for t in trades)
    realized = sum(float(t["pnl"] or 0) for t in closed)
    wins = len([t for t in closed if float(t["pnl"] or 0) > 0])
    return {
        "total_trades": len(trades), "open_trades": len(open_t),
        "closed_trades": len(closed), "total_invested": invested,
        "realized_pnl": realized,
        "win_rate": round(wins / len(closed) * 100, 1) if closed else 0.0,
        "roi_pct": round(realized / invested * 100, 2) if invested else 0.0,
        "trades": trades,
    }


# --- backtest persistence ---------------------------------------------------

def record_backtest_run(user_id: Optional[str], city: str, result: Dict[str, Any],
                        config: Optional[dict] = None) -> str:
    """Persist a backtest result: a run row + a backtest_summaries row + trades."""
    from sqlalchemy import text
    run_id = f"pred-bt-{uuid.uuid4().hex[:12]}"
    ensure_run(run_id, "backtest", user_id=user_id, config={"city": city, **(config or {})})

    total_invested = float(result.get("total_invested", 0) or 0)
    final_pnl = float(result.get("final_pnl", 0) or 0)
    final_roi = float(result.get("final_roi", 0) or 0)
    trades = result.get("trades", []) or []
    wins = len([t for t in trades if "WIN" in str(t.get("result", ""))])
    closed = len([t for t in trades if "PENDING" not in str(t.get("result", "")) and t.get("Side", "NONE") != "NONE"])
    win_rate = round(wins / closed * 100, 4) if closed else 0.0

    with _pool().get_session() as s:
        s.execute(text("""
            INSERT INTO assethero.backtest_summaries
                (run_id, user_id, variation_index, strategy_slug, params,
                 total_return, total_pnl, win_rate, total_trades, is_best)
            VALUES
                (:run_id, :user_id, 0, :slug, :params,
                 :total_return, :total_pnl, :win_rate, :total_trades, TRUE)
        """), {
            "run_id": run_id, "user_id": user_id,
            "slug": f"weather-{city}-{result.get('period', '')}"[:128],
            "params": __import__("json").dumps(config or {}, default=str),
            "total_return": final_roi, "total_pnl": final_pnl,
            "win_rate": win_rate, "total_trades": len(trades),
        })
        for t in trades:
            side = t.get("Side", "NONE")
            if side == "NONE":
                continue
            price = float(t.get("price", 0) or 0)
            if price <= 0:
                continue
            shares = 100.0 / price
            res = str(t.get("result", ""))
            exit_price = 1.0 if "WIN" in res else (0.0 if "LOSS" in res else None)
            pnl = (shares * exit_price - 100.0) if exit_price is not None else None
            s.execute(text("""
                INSERT INTO assethero.trades
                    (run_id, user_id, trade_type, vertical, venue, symbol, direction,
                     shares, entry_price, exit_price, pnl, reason)
                VALUES
                    (:run_id, :user_id, 'backtest', :vertical, :venue, :symbol, :direction,
                     :shares, :entry_price, :exit_price, :pnl, :reason)
            """), {
                "run_id": run_id, "user_id": user_id, "vertical": VERTICAL, "venue": VENUE,
                "symbol": str(t.get("market_id", ""))[:16], "direction": side[:8],
                "shares": shares, "entry_price": price, "exit_price": exit_price,
                "pnl": pnl, "reason": (str(t.get("market_name", "")))[:500],
            })

    complete_run(run_id, "completed",
                 results={"final_roi": final_roi, "final_pnl": final_pnl,
                          "trades": len(trades)})
    return run_id
