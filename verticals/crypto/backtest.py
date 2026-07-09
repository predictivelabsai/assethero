"""Crypto backtest runner.

Drives a crypto strategy over historical OHLCV (fetched via engine.feeds.ccxt_feed)
with the reusable RL hyperparameter tuner (engine.backtest.tuner). Ported from
rl-agent-swarm `tasks/backtest.py` + `tasks/trading_engine.py`.

Scope: BACKTEST only. `order_book` and `arbitrage` are live-only and rejected
here. All heavy deps (ccxt/numpy/pandas) are imported lazily by the feed and the
strategies, so importing this module is cheap.

Optionally persists a run to the shared assethero.runs / trades /
backtest_summaries tables when a DATABASE_URL and user_id are available; failures
to persist never abort the backtest.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class CryptoBacktestResult:
    agent_type: str
    exchange: str
    symbol: str
    timeframe: str
    initial_balance: float
    final_balance: float
    total_pnl: float
    total_return: float          # fraction
    total_trades: int
    win_rate: float              # fraction
    sharpe: float
    max_drawdown: float          # fraction
    initial_params: Dict[str, Any]
    final_params: Dict[str, Any]
    trades: List[Dict[str, Any]] = field(default_factory=list)
    run_id: Optional[str] = None
    error: Optional[str] = None


def _state_vector(prev_closes):
    """RL state = last-5 returns + 4 seasonality zeros + volatility."""
    import numpy as np
    arr = np.asarray(prev_closes, dtype=float)
    if len(arr) < 2:
        returns = np.zeros(5)
        vol = 0.0
    else:
        rets = np.diff(arr) / arr[:-1]
        returns = rets[-5:]
        if len(returns) < 5:
            returns = np.pad(returns, (5 - len(returns), 0))
        vol = float(np.std(rets))
    return np.concatenate([returns, np.zeros(4), [vol]])


def run_backtest(agent_type: str, exchange: str = "kraken", symbol: str = "BTC/USDC",
                 timeframe: str = "1m", limit: int = 1000,
                 params: Optional[Dict[str, Any]] = None,
                 initial_balance: float = 10000.0,
                 user_id: Optional[str] = None,
                 use_rl_tuner: bool = True,
                 persist: bool = True) -> CryptoBacktestResult:
    """Run a single-symbol crypto backtest and return metrics + trades."""
    from .config import AGENT_CONFIGS, BACKTEST_AGENTS, merged_config
    from .strategies import build_strategy, Position
    from engine.feeds.ccxt_feed import CCXTFeed
    import numpy as np

    if agent_type not in AGENT_CONFIGS:
        raise ValueError(f"Unknown crypto agent: {agent_type}")
    if agent_type not in BACKTEST_AGENTS:
        raise ValueError(f"'{agent_type}' is live-only and cannot be backtested.")

    cfg = merged_config(agent_type, params)
    strategy = build_strategy(agent_type, cfg)

    tuner = None
    if use_rl_tuner and AGENT_CONFIGS[agent_type]["tunable_params"]:
        from engine.backtest.tuner import RLHyperparameterTuner
        tuner_cfg = dict(cfg)
        tuner_cfg["tunable_params"] = AGENT_CONFIGS[agent_type]["tunable_params"]
        tuner_cfg["state_size"] = 10
        tuner = RLHyperparameterTuner(strategy, tuner_cfg)

    initial_params = {k: getattr(strategy, k, None)
                      for k in AGENT_CONFIGS[agent_type]["tunable_params"]}

    # --- fetch data ---
    feed = CCXTFeed(exchange, user_id=user_id)
    df = feed.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if df is None or df.empty or len(df) < 60:
        return CryptoBacktestResult(
            agent_type, exchange, symbol, timeframe, initial_balance,
            initial_balance, 0.0, 0.0, 0, 0.0, 0.0, 0.0,
            initial_params, initial_params, [], None,
            error="Insufficient market data returned by exchange.")

    closes = df["close"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    vols = df["volume"].tolist() if "volume" in df.columns else [0] * len(df)
    times = df["timestamp"].tolist()

    balance = initial_balance
    position = 0.0
    entry_price = 0.0
    entry_time = None
    trades: List[Dict[str, Any]] = []
    equity_curve: List[float] = []
    warmup = 50

    for i in range(warmup, len(df)):
        prev_closes = closes[i - warmup:i]
        price = closes[i]
        ts = times[i]

        if tuner is not None:
            tuner.update_parameters(_state_vector(prev_closes))

        market_data = {symbol: {
            "close": price,
            "high": highs[i], "low": lows[i], "volume": vols[i],
            "close_history": prev_closes,
            "high_history": highs[i - warmup:i],
            "low_history": lows[i - warmup:i],
            "volume_history": vols[i - warmup:i],
        }}
        positions = []
        if position != 0:
            positions.append(Position(symbol, abs(position), entry_price, "pos_1"))
        context = {"positions": positions, "total_pnl": balance - initial_balance,
                   "account_value": balance}

        decision = strategy.act({"market_data": market_data}, context)
        action = decision.get("action")
        size = decision.get("size", 0) or 0
        reason = decision.get("reason", "")
        step_pnl = 0.0

        if action == "BUY" and position == 0:
            cost = size * price
            if balance >= cost and size > 0:
                balance -= cost
                position += size
                entry_price = price
                entry_time = ts
        elif action == "SELL" and position > 0:
            sell_size = min(size, position) if size else position
            balance += sell_size * price
            trade_pnl = (price - entry_price) * sell_size
            step_pnl = trade_pnl
            trades.append({
                "symbol": symbol, "direction": "long", "shares": sell_size,
                "entry_time": entry_time, "exit_time": ts,
                "entry_price": entry_price, "exit_price": price,
                "pnl": trade_pnl,
                "pnl_pct": ((price - entry_price) / entry_price) if entry_price else 0.0,
                "capital_after": balance,
                "hit_target": "TAKE_PROFIT" in reason or "PROFIT" in reason,
                "hit_stop": "STOP_LOSS" in reason,
                "reason": reason,
            })
            position -= sell_size
            if position <= 0:
                entry_time = None

        if tuner is not None:
            tuner.learn(step_pnl, _state_vector(prev_closes), done=(i == len(df) - 1))
        equity_curve.append(balance + position * price)

    final_balance = balance + position * closes[-1]
    total_pnl = final_balance - initial_balance
    total_return = total_pnl / initial_balance if initial_balance else 0.0
    wins = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = wins / len(trades) if trades else 0.0

    eq = np.asarray(equity_curve, dtype=float)
    if len(eq) > 1:
        rets = np.diff(eq) / np.where(eq[:-1] == 0, 1, eq[:-1])
        sharpe = float(np.mean(rets) / np.std(rets) * np.sqrt(252)) if np.std(rets) > 0 else 0.0
        peak = np.maximum.accumulate(eq)
        dd = (eq - peak) / np.where(peak == 0, 1, peak)
        max_dd = float(abs(dd.min()))
    else:
        sharpe = 0.0
        max_dd = 0.0

    final_params = {k: getattr(strategy, k, None)
                    for k in AGENT_CONFIGS[agent_type]["tunable_params"]}

    result = CryptoBacktestResult(
        agent_type, exchange, symbol, timeframe, initial_balance, final_balance,
        total_pnl, total_return, len(trades), win_rate, sharpe, max_dd,
        initial_params, final_params, trades)

    if persist:
        try:
            result.run_id = _persist_run(result, cfg, user_id)
        except Exception as e:  # noqa: BLE001 — persistence is best-effort
            logger.warning("crypto backtest persist failed: %s", e)

    return result


def _persist_run(res: CryptoBacktestResult, cfg: Dict[str, Any],
                 user_id: Optional[str]) -> Optional[str]:
    """Best-effort write into shared assethero.runs + backtest_summaries + trades."""
    import json
    from sqlalchemy import text
    from utils.db.db_pool import DatabasePool

    run_id = f"crypto-bt-{uuid.uuid4().hex[:12]}"
    slug = f"{res.agent_type}-{res.exchange}-{res.symbol.replace('/', '')}-{res.timeframe}"
    now = datetime.now(timezone.utc)
    pool = DatabasePool()
    with pool.get_session() as s:
        s.execute(text("""
            INSERT INTO assethero.runs
              (run_id, user_id, vertical, mode, strategy, strategy_slug, symbols,
               status, config, results, started_at, completed_at)
            VALUES
              (:run_id, :user_id, 'crypto', 'backtest', :strategy, :slug, :symbols,
               'completed', :config, :results, :now, :now)
        """), {
            "run_id": run_id, "user_id": user_id, "strategy": res.agent_type,
            "slug": slug, "symbols": [res.symbol],
            "config": json.dumps({"exchange": res.exchange, "timeframe": res.timeframe, **cfg}),
            "results": json.dumps({
                "total_return": res.total_return, "total_pnl": res.total_pnl,
                "win_rate": res.win_rate, "sharpe": res.sharpe,
                "max_drawdown": res.max_drawdown, "final_params": res.final_params,
            }, default=str),
            "now": now,
        })
        s.execute(text("""
            INSERT INTO assethero.backtest_summaries
              (run_id, user_id, variation_index, strategy_slug, params,
               total_return, total_pnl, win_rate, total_trades, sharpe_ratio,
               max_drawdown, is_best)
            VALUES
              (:run_id, :user_id, 0, :slug, :params,
               :total_return, :total_pnl, :win_rate, :total_trades, :sharpe,
               :max_drawdown, TRUE)
        """), {
            "run_id": run_id, "user_id": user_id, "slug": slug,
            "params": json.dumps(res.final_params, default=str),
            "total_return": res.total_return * 100, "total_pnl": res.total_pnl,
            "win_rate": res.win_rate, "total_trades": res.total_trades,
            "sharpe": res.sharpe, "max_drawdown": res.max_drawdown,
        })
        for t in res.trades:
            s.execute(text("""
                INSERT INTO assethero.trades
                  (run_id, user_id, trade_type, strategy_slug, symbol, direction,
                   shares, entry_time, exit_time, entry_price, exit_price,
                   hit_target, hit_stop, pnl, pnl_pct, capital_after, reason)
                VALUES
                  (:run_id, :user_id, 'backtest', :slug, :symbol, :direction,
                   :shares, :entry_time, :exit_time, :entry_price, :exit_price,
                   :hit_target, :hit_stop, :pnl, :pnl_pct, :capital_after, :reason)
            """), {
                "run_id": run_id, "user_id": user_id, "slug": slug,
                "symbol": t["symbol"], "direction": t["direction"], "shares": t["shares"],
                "entry_time": t["entry_time"], "exit_time": t["exit_time"],
                "entry_price": t["entry_price"], "exit_price": t["exit_price"],
                "hit_target": t["hit_target"], "hit_stop": t["hit_stop"],
                "pnl": t["pnl"], "pnl_pct": t["pnl_pct"] * 100,
                "capital_after": t["capital_after"], "reason": t["reason"],
            })
    return run_id
