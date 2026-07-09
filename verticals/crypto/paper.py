"""Crypto paper-trading session (simulated fills, no live execution).

Ported from rl-agent-swarm `tasks/run_paper_trading.py` (single-symbol
PaperTradingSession) and pared down to the platform's BACKTEST + PAPER scope:
fills are simulated in-process via engine.brokers.ccxt_broker (paper=True) and no
live order ever reaches an exchange. RL tuning uses engine.backtest.tuner.

Designed to be driven either as a bounded loop (`run_cycles(n)` for the web,
which polls live tickers a fixed number of times) or indefinitely
(`run_forever`) from a CLI/worker. Heavy deps are imported lazily.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CryptoPaperSession:
    """Single-symbol crypto paper-trading session with simulated fills."""

    def __init__(self, agent_type: str, exchange: str = "kraken",
                 symbol: str = "BTC/USDC", params: Optional[Dict[str, Any]] = None,
                 initial_balance: float = 10000.0, timeframe: str = "1m",
                 user_id: Optional[str] = None, use_rl_tuner: bool = True):
        from .config import AGENT_CONFIGS, PAPER_AGENTS, merged_config
        from .strategies import build_strategy
        from engine.feeds.ccxt_feed import CCXTFeed
        from engine.brokers.ccxt_broker import CCXTBroker

        if agent_type not in PAPER_AGENTS:
            raise ValueError(f"'{agent_type}' is not available for the paper loop.")

        self.agent_type = agent_type
        self.exchange = exchange
        self.symbol = symbol
        self.timeframe = timeframe
        self.user_id = user_id
        self.run_id = f"crypto-paper-{uuid.uuid4().hex[:12]}"

        self.cfg = merged_config(agent_type, params)
        self.strategy = build_strategy(agent_type, self.cfg)
        self.feed = CCXTFeed(exchange, user_id=user_id)
        # allow_live stays False: every fill is simulated (paper=True).
        self.broker = CCXTBroker(exchange, user_id=user_id, allow_live=False)

        self.tuner = None
        if use_rl_tuner and AGENT_CONFIGS[agent_type]["tunable_params"]:
            from engine.backtest.tuner import RLHyperparameterTuner
            tuner_cfg = dict(self.cfg)
            tuner_cfg["tunable_params"] = AGENT_CONFIGS[agent_type]["tunable_params"]
            tuner_cfg["state_size"] = 10
            self.tuner = RLHyperparameterTuner(self.strategy, tuner_cfg)

        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.position = 0.0
        self.entry_price = 0.0
        self.entry_time = None
        self.trades: List[Dict[str, Any]] = []
        self.history: List[float] = []

        # Warmup history so indicators have data on the first cycle.
        try:
            df = self.feed.fetch_ohlcv(symbol, timeframe=timeframe, limit=60)
            if df is not None and not df.empty:
                self.history = df["close"].tolist()
        except Exception as e:  # noqa: BLE001
            logger.warning("crypto paper warmup fetch failed: %s", e)

    def _state_vector(self):
        import numpy as np
        arr = np.asarray(self.history[-50:], dtype=float)
        if len(arr) < 2:
            return np.zeros(10)
        rets = np.diff(arr) / np.where(arr[:-1] == 0, 1, arr[:-1])
        returns = rets[-5:]
        if len(returns) < 5:
            returns = np.pad(returns, (5 - len(returns), 0))
        return np.concatenate([returns, np.zeros(4), [float(np.std(rets))]])

    def step(self) -> Dict[str, Any]:
        """Run one paper cycle: fetch price, decide, simulate a fill."""
        from .strategies import Position
        ticker = self.feed.fetch_ticker(self.symbol)
        price = float(ticker.get("last"))
        ts = datetime.now(timezone.utc)
        self.history.append(price)
        if len(self.history) > 200:
            self.history.pop(0)

        if len(self.history) < 30:
            return {"action": "WARMUP", "price": price, "balance": self.balance}

        if self.tuner is not None:
            self.tuner.update_parameters(self._state_vector())

        market_data = {self.symbol: {
            "close": price,
            "high": price, "low": price, "volume": 0,
            "close_history": self.history[-60:],
            "high_history": self.history[-60:],
            "low_history": self.history[-60:],
        }}
        positions = []
        if self.position != 0:
            positions.append(Position(self.symbol, abs(self.position), self.entry_price, "pos_1"))
        context = {"positions": positions, "total_pnl": self.balance - self.initial_balance,
                   "account_value": self.balance}

        decision = self.strategy.act({"market_data": market_data}, context)
        step_pnl = self._execute(decision, price, ts)

        if self.tuner is not None:
            self.tuner.learn(step_pnl, self._state_vector(), done=False)
        return {"action": decision.get("action"), "reason": decision.get("reason"),
                "price": price, "balance": self.balance, "position": self.position}

    def _execute(self, decision, price, ts) -> float:
        action = decision.get("action")
        size = decision.get("size", 0) or 0
        reason = decision.get("reason", "")
        step_pnl = 0.0
        if action == "BUY" and self.position == 0 and size > 0:
            fill = self.broker.submit_order(self.symbol, "buy", size, price=price, paper=True)
            cost = size * fill["price"]
            if self.balance >= cost:
                self.balance -= cost
                self.position += size
                self.entry_price = fill["price"]
                self.entry_time = ts
        elif action == "SELL" and self.position > 0:
            sell_size = min(size, self.position) if size else self.position
            fill = self.broker.submit_order(self.symbol, "sell", sell_size, price=price, paper=True)
            self.balance += sell_size * fill["price"]
            trade_pnl = (fill["price"] - self.entry_price) * sell_size
            step_pnl = trade_pnl
            self.trades.append({
                "symbol": self.symbol, "direction": "long", "shares": sell_size,
                "entry_time": self.entry_time, "exit_time": ts,
                "entry_price": self.entry_price, "exit_price": fill["price"],
                "pnl": trade_pnl,
                "pnl_pct": ((fill["price"] - self.entry_price) / self.entry_price) if self.entry_price else 0.0,
                "capital_after": self.balance,
                "hit_target": "TAKE_PROFIT" in reason or "PROFIT" in reason,
                "hit_stop": "STOP_LOSS" in reason, "reason": reason,
            })
            self.position -= sell_size
            if self.position <= 0:
                self.entry_time = None
        return step_pnl

    def run_cycles(self, n: int = 5, interval_sec: float = 0.0) -> Dict[str, Any]:
        """Run a bounded number of paper cycles (used by the web handler)."""
        events = []
        for i in range(max(1, n)):
            try:
                events.append(self.step())
            except Exception as e:  # noqa: BLE001
                events.append({"action": "ERROR", "error": str(e)})
                break
            if interval_sec and i < n - 1:
                time.sleep(interval_sec)
        return self.summary(events)

    def run_forever(self, interval_sec: int = 60):
        """Indefinite loop for a CLI/worker (paper only). Ctrl+C to stop."""
        logger.info("Crypto paper session %s: %s on %s (%s)",
                    self.run_id, self.agent_type, self.exchange, self.symbol)
        try:
            while True:
                self.step()
                time.sleep(interval_sec)
        except KeyboardInterrupt:
            logger.info("Paper session stopped. Summary: %s", self.summary())

    def summary(self, events: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        final = self.balance + self.position * (self.history[-1] if self.history else 0)
        wins = sum(1 for t in self.trades if t["pnl"] > 0)
        return {
            "run_id": self.run_id, "agent_type": self.agent_type,
            "exchange": self.exchange, "symbol": self.symbol,
            "final_balance": final, "total_pnl": final - self.initial_balance,
            "total_trades": len(self.trades),
            "win_rate": (wins / len(self.trades)) if self.trades else 0.0,
            "open_position": self.position, "trades": self.trades,
            "events": events or [],
        }


def run_paper(agent_type: str, exchange: str = "kraken", symbol: str = "BTC/USDC",
              params: Optional[Dict[str, Any]] = None, cycles: int = 5,
              initial_balance: float = 10000.0,
              user_id: Optional[str] = None) -> Dict[str, Any]:
    """Convenience: build a session and run `cycles` paper steps."""
    session = CryptoPaperSession(agent_type, exchange, symbol, params,
                                 initial_balance=initial_balance, user_id=user_id)
    return session.run_cycles(cycles)
