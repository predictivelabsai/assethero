"""Crypto trading strategies (8) ported from rl-agent-swarm/agents/*.

Each strategy exposes ``act(state, context) -> decision`` where:
  state   = {"market_data": {symbol: {close, close_history, high, low, ...}}}
  context = {"positions": [Position(symbol, size, entry_price, position_id)], ...}
  decision= {"action": BUY|SELL|HOLD|ARBITRAGE, "symbol", "size", "reason", ...}

This mirrors the original React-pattern agents but drops the DB/repository
plumbing (the backtest/paper engine supplies positions via `context`). Technical
indicators (RSI, ADX, Bollinger, box/wedge) are reimplemented on numpy/pandas so
the `ta` package is NOT required. All heavy imports (numpy/pandas) are done
inside methods so importing this module is cheap and dependency-free.
"""
from __future__ import annotations

import logging
from collections import namedtuple
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Lightweight position record used by the engine's mocked context.
Position = namedtuple("Position", ["symbol", "size", "entry_price", "position_id"])


# --- indicator helpers (numpy/pandas, no `ta`) ------------------------------

def _sma(values, period):
    import numpy as np
    arr = np.asarray(values[-period:], dtype=float)
    return float(arr.mean()) if len(arr) else 0.0


def _rsi(closes, period=14):
    import numpy as np
    closes = np.asarray(closes[-(period + 1):], dtype=float)
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _adx(highs, lows, closes, period=14):
    """Wilder ADX on plain numpy — returns the latest ADX value."""
    import numpy as np
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    n = min(len(h), len(l), len(c))
    if n < period * 2:
        return 0.0
    h, l, c = h[-n:], l[-n:], c[-n:]
    up = h[1:] - h[:-1]
    dn = l[:-1] - l[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = np.maximum.reduce([
        h[1:] - l[1:],
        np.abs(h[1:] - c[:-1]),
        np.abs(l[1:] - c[:-1]),
    ])

    def _wilder(x):
        out = np.zeros_like(x)
        if len(x) < period:
            return out
        out[period - 1] = x[:period].sum()
        for i in range(period, len(x)):
            out[i] = out[i - 1] - (out[i - 1] / period) + x[i]
        return out

    atr = _wilder(tr)
    plus_di = 100.0 * np.divide(_wilder(plus_dm), atr, out=np.zeros_like(atr), where=atr != 0)
    minus_di = 100.0 * np.divide(_wilder(minus_dm), atr, out=np.zeros_like(atr), where=atr != 0)
    denom = plus_di + minus_di
    dx = 100.0 * np.divide(np.abs(plus_di - minus_di), denom, out=np.zeros_like(denom), where=denom != 0)
    valid = dx[period:]
    if len(valid) == 0:
        return 0.0
    return float(valid[-period:].mean()) if len(valid) >= period else float(valid.mean())


# --- base -------------------------------------------------------------------

class BaseStrategy:
    agent_type = "base"
    strategy_name = "Base"

    def __init__(self, agent_id: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.config = config or {}
        self.positions: Dict[str, float] = {}

    def act(self, state: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _hold(symbol=None, reason="No signal"):
        return {"action": "HOLD", "symbol": symbol, "size": 0, "reason": reason}


# --- 1. Momentum ------------------------------------------------------------

class MomentumStrategy(BaseStrategy):
    agent_type = "momentum"
    strategy_name = "Momentum (MA Crossover + RSI/ADX)"

    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        c = config
        self.fast_ma_period = int(c.get("fast_ma_period", 8))
        self.slow_ma_period = int(c.get("slow_ma_period", 21))
        self.rsi_period = int(c.get("rsi_period", 14))
        self.rsi_upper = c.get("rsi_upper", 75)
        self.rsi_lower = c.get("rsi_lower", 30)
        self.adx_period = int(c.get("adx_period", 14))
        self.adx_threshold = c.get("adx_threshold", 15)
        self.position_size = c.get("position_size", 0.08)
        self.profit_percentage = c.get("profit_percentage", 0.02)
        self.stop_loss_percentage = c.get("stop_loss_percentage", 0.015)

    def act(self, state, context):
        import numpy as np
        market_data = state.get("market_data", {})
        positions = context.get("positions", [])
        decision = self._hold()
        for symbol, data in market_data.items():
            closes = data.get("close_history", [])
            highs = data.get("high_history", [])
            lows = data.get("low_history", [])
            if not closes or len(closes) < self.slow_ma_period + 2:
                continue
            current_price = data.get("close")
            fast_ma = _sma(closes, self.fast_ma_period)
            slow_ma = _sma(closes, self.slow_ma_period)
            prev_fast = _sma(closes[:-1], self.fast_ma_period)
            prev_slow = _sma(closes[:-1], self.slow_ma_period)
            rsi = _rsi(closes, self.rsi_period)
            adx = _adx(highs or closes, lows or closes, closes, self.adx_period)
            ma_gap_pct = ((fast_ma - slow_ma) / slow_ma * 100) if slow_ma else 0
            cross_dir = "above" if fast_ma > slow_ma else "below"
            pos = next((p for p in positions if p.symbol == symbol), None)
            if pos:
                if prev_fast >= prev_slow and fast_ma < slow_ma:
                    return self._sell(symbol, pos.size, f"MA_CROSSOVER_EXIT ({fast_ma:.2f}<{slow_ma:.2f})")
                if rsi > self.rsi_upper:
                    return self._sell(symbol, pos.size, f"RSI_OVERBOUGHT_EXIT ({rsi:.1f})")
                if current_price >= pos.entry_price * (1 + self.profit_percentage):
                    return self._sell(symbol, pos.size, f"TAKE_PROFIT_HIT (+{self.profit_percentage:.1%})")
                if current_price <= pos.entry_price * (1 - self.stop_loss_percentage):
                    return self._sell(symbol, pos.size, f"STOP_LOSS_HIT (-{self.stop_loss_percentage:.1%})")
                decision = self._hold(symbol, f"Holding {symbol} | gap={ma_gap_pct:+.2f}% RSI={rsi:.0f} ADX={adx:.0f}")
            else:
                if adx < self.adx_threshold:
                    decision = self._hold(symbol, f"Scan {symbol} | ADX={adx:.0f}<{self.adx_threshold} RSI={rsi:.0f}")
                    continue
                if rsi > self.rsi_upper:
                    decision = self._hold(symbol, f"Scan {symbol} | RSI={rsi:.0f} overbought")
                    continue
                if prev_fast <= prev_slow and fast_ma > slow_ma:
                    return self._buy(symbol, f"MOMENTUM_BUY (MA cross, RSI={rsi:.1f}, ADX={adx:.1f})")
                if fast_ma > slow_ma and self.rsi_lower < rsi < 50:
                    return self._buy(symbol, f"TREND_BUY (Fast {cross_dir} +{abs(ma_gap_pct):.2f}%, RSI={rsi:.1f})")
                decision = self._hold(symbol, f"Waiting {symbol} | Fast {cross_dir} by {abs(ma_gap_pct):.2f}%")
        return decision

    def _buy(self, symbol, reason):
        return {"action": "BUY", "symbol": symbol, "size": self.position_size,
                "reason": reason, "strategy_name": self.strategy_name}

    def _sell(self, symbol, size, reason):
        return {"action": "SELL", "symbol": symbol, "size": size,
                "reason": reason, "strategy_name": self.strategy_name}


# --- 2. Mean Reversion ------------------------------------------------------

class MeanReversionStrategy(BaseStrategy):
    agent_type = "mean_reversion"
    strategy_name = "Mean Reversion (BB+RSI)"

    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        c = config
        self.bb_period = int(c.get("bb_period", 14))
        self.bb_std = c.get("bb_std", 1.8)
        self.rsi_period = int(c.get("rsi_period", 14))
        self.rsi_threshold = c.get("rsi_threshold", 35)
        self.volume_mult = c.get("volume_mult", 0.8)
        self.position_size = c.get("position_size", 0.05)
        self.stop_loss_pct = c.get("stop_loss_pct", 0.02)

    def _bollinger(self, closes):
        import numpy as np
        arr = np.asarray(closes[-self.bb_period:], dtype=float)
        if len(arr) < 5:
            return 0, 0, float(arr[-1]) if len(arr) else 0, 0
        sma = arr.mean()
        std = arr.std()
        return sma + self.bb_std * std, sma - self.bb_std * std, sma, std

    def act(self, state, context):
        market_data = state.get("market_data", {})
        decision = self._hold()
        for symbol, data in market_data.items():
            closes = data.get("close_history", [])
            if not closes or "close" not in data:
                continue
            upper, lower, mid, std = self._bollinger(closes)
            rsi = _rsi(closes, self.rsi_period)
            price = data.get("close")
            dyn_stop = (std / price) if price > 0 else self.stop_loss_pct
            active_stop = max(self.stop_loss_pct, dyn_stop)
            width = upper - lower if upper > lower else 1
            bb_pos = ((price - lower) / width * 100) if width else 50
            if price <= lower and rsi < self.rsi_threshold:
                return self._buy(symbol, f"BB_LOWER_RSI_OVERSOLD (RSI={rsi:.1f}, BB={bb_pos:.0f}%)", price, active_stop, mid)
            if bb_pos < 10 and rsi < 45:
                return self._buy(symbol, f"BB_NEAR_LOWER (RSI={rsi:.1f}, BB={bb_pos:.0f}%)", price, active_stop, mid)
            if price >= upper and rsi > 70:
                return {"action": "SELL", "symbol": symbol, "size": self.position_size,
                        "reason": f"BB_UPPER_RSI_OVERBOUGHT (RSI={rsi:.1f})", "strategy_name": self.strategy_name}
            decision = self._hold(symbol, f"Scan {symbol} | BB={bb_pos:.0f}% RSI={rsi:.0f}")
        return decision

    def _buy(self, symbol, reason, price, stop, tp):
        return {"action": "BUY", "symbol": symbol, "size": self.position_size, "reason": reason,
                "entry_price": price, "stop_loss": price * (1 - stop), "take_profit": tp,
                "strategy_name": self.strategy_name}


# --- 3. Buy The Dip ---------------------------------------------------------

class BuyTheDipStrategy(BaseStrategy):
    agent_type = "buy_the_dip"
    strategy_name = "Buy The Dip"

    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        c = config
        self.sma_period = int(c.get("sma_period", 14))
        self.dip_percentage = c.get("dip_percentage", 0.005)
        self.profit_percentage = c.get("profit_percentage", 0.015)
        self.stop_loss_percentage = c.get("stop_loss_percentage", 0.015)
        self.position_size = c.get("position_size", 0.08)

    def act(self, state, context):
        market_data = state.get("market_data", {})
        positions = context.get("positions", [])
        decision = self._hold()
        for symbol, data in market_data.items():
            closes = data.get("close_history", [])
            if "close" not in data or not closes:
                continue
            price = data.get("close")
            pos = next((p for p in positions if p.symbol == symbol), None)
            if pos:
                if price >= pos.entry_price * (1 + self.profit_percentage):
                    return self._sell(symbol, pos.size, f"TAKE_PROFIT_HIT (+{self.profit_percentage:.1%})")
                if price <= pos.entry_price * (1 - self.stop_loss_percentage):
                    return self._sell(symbol, pos.size, f"STOP_LOSS_HIT (-{self.stop_loss_percentage:.1%})")
            else:
                if len(closes) < self.sma_period:
                    continue
                sma = _sma(closes, self.sma_period)
                if sma <= 0:
                    continue
                threshold = sma * (1 - self.dip_percentage)
                dist_pct = ((price - sma) / sma * 100) if sma else 0
                if price <= threshold:
                    return self._buy(symbol, f"DIP_DETECTED (Price {price:.2f}<SMA {sma:.2f})")
                decision = self._hold(symbol, f"Scan {symbol} | {dist_pct:+.2f}% from SMA")
        return decision

    def _buy(self, symbol, reason):
        return {"action": "BUY", "symbol": symbol, "size": self.position_size,
                "reason": reason, "strategy_name": self.strategy_name}

    def _sell(self, symbol, size, reason):
        return {"action": "SELL", "symbol": symbol, "size": size,
                "reason": reason, "strategy_name": self.strategy_name}


# --- 4. Market Making -------------------------------------------------------

class MarketMakingStrategy(BaseStrategy):
    agent_type = "market_making"
    strategy_name = "Simple Market Making"

    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        c = config
        self.sma_period = int(c.get("sma_period", 5))
        self.spread_pct = c.get("spread_pct", 0.004)
        self.position_limit = c.get("position_limit", 1.0)
        self.order_size = c.get("order_size", 0.1)

    def act(self, state, context):
        market_data = state.get("market_data", {})
        positions = context.get("positions", [])
        decision = self._hold()
        for symbol, data in market_data.items():
            closes = data.get("close_history", [])
            if "close" not in data or not closes:
                continue
            price = data.get("close")
            fair = _sma(closes, self.sma_period) if len(closes) >= self.sma_period else price
            if fair == 0:
                continue
            half = self.spread_pct / 2
            bid, ask = fair * (1 - half), fair * (1 + half)
            pos = next((p for p in positions if p.symbol == symbol), None)
            size = pos.size if pos else 0
            if price <= bid and size < self.position_limit:
                return {"action": "BUY", "symbol": symbol, "size": self.order_size,
                        "reason": f"MARKET_MAKE_BUY (Price {price:.2f}<=Bid {bid:.2f})",
                        "strategy_name": self.strategy_name}
            if price >= ask and size > -self.position_limit:
                return {"action": "SELL", "symbol": symbol, "size": self.order_size,
                        "reason": f"MARKET_MAKE_SELL (Price {price:.2f}>=Ask {ask:.2f})",
                        "strategy_name": self.strategy_name}
            decision = self._hold(symbol, f"Quoting {symbol} | bid={bid:.2f} ask={ask:.2f}")
        return decision


# --- 5. Box & Wedge ---------------------------------------------------------

class BoxWedgeStrategy(BaseStrategy):
    agent_type = "box_wedge"
    strategy_name = "Box & Wedge"

    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        c = config
        self.sma_period = int(c.get("sma_period", 50))
        self.box_lookback = int(c.get("box_lookback", 12))
        self.volatility_threshold = c.get("volatility_threshold", 0.8)
        self.wedge_lookback = int(c.get("wedge_lookback", 3))
        self.risk_per_trade = c.get("risk_per_trade", 0.015)
        self.scale_out_1r = c.get("scale_out_1r", 1.5)
        self.scale_out_2r = c.get("scale_out_2r", 3.0)
        self.runner_percentage = c.get("runner_percentage", 0.25)
        self.active_positions: Dict[str, Any] = {}

    def act(self, state, context):
        import numpy as np
        import pandas as pd
        market_data = state.get("market_data", {})
        positions = context.get("positions", [])
        account_value = context.get("account_value", 10000)
        decision = self._hold()

        # Manage existing positions (scale-out at R multiples).
        for position in positions:
            symbol = position.symbol
            data = market_data.get(symbol)
            if not data:
                continue
            price = data.get("close")
            entry = position.entry_price
            stop = self.active_positions.get(symbol, {}).get("stop_price", entry * 0.99)
            risk = abs(entry - stop) or entry * 0.01
            t1, t2 = entry + risk * self.scale_out_1r, entry + risk * self.scale_out_2r
            if price <= stop:
                self.active_positions.pop(symbol, None)
                return self._sell(symbol, position.size, "STOP_LOSS_HIT")
            if price >= t2:
                self.active_positions.pop(symbol, None)
                return self._sell(symbol, position.size, f"SCALE_OUT_3R ({t2:.2f})")
            if price >= t1:
                return self._sell(symbol, position.size * 0.5, f"SCALE_OUT_1.5R ({t1:.2f})")

        # Look for new entries.
        for symbol, data in market_data.items():
            closes = data.get("close_history", [])
            highs = data.get("high_history", [])
            lows = data.get("low_history", [])
            if len(closes) < self.sma_period or not highs or not lows:
                continue
            if any(p.symbol == symbol for p in positions):
                continue
            df = pd.DataFrame({
                "Close": closes[-self.sma_period * 2:],
                "High": highs[-self.sma_period * 2:],
                "Low": lows[-self.sma_period * 2:],
            })
            sma = df["Close"].rolling(self.sma_period).mean()
            if pd.isna(sma.iloc[-1]) or df["Close"].iloc[-1] <= sma.iloc[-1]:
                continue  # not bullish regime
            rng = df["High"].rolling(self.box_lookback).max() - df["Low"].rolling(self.box_lookback).min()
            avg_rng = rng.rolling(self.sma_period).mean()
            if pd.isna(rng.iloc[-1]) or pd.isna(avg_rng.iloc[-1]):
                continue
            if rng.iloc[-1] >= avg_rng.iloc[-1] * self.volatility_threshold:
                continue  # not in a box contraction
            wedge_high = df["High"].iloc[-self.wedge_lookback:].max()
            price = df["Close"].iloc[-1]
            if price > wedge_high:
                wedge_low = df["Low"].iloc[-self.wedge_lookback:].min()
                stop = wedge_low * 0.995
                risk_per_unit = abs(price - stop) or price * 0.01
                size_units = (account_value * self.risk_per_trade) / risk_per_unit
                position_pct = min((size_units * price) / account_value, 0.15)
                self.active_positions[symbol] = {"entry_price": price, "stop_price": stop}
                return {"action": "BUY", "symbol": symbol, "size": position_pct,
                        "reason": f"WEDGE_BREAKOUT (break {price:.2f}, stop {stop:.2f})",
                        "strategy_name": self.strategy_name}
        return decision

    def _sell(self, symbol, size, reason):
        return {"action": "SELL", "symbol": symbol, "size": size,
                "reason": reason, "strategy_name": self.strategy_name}


# --- 6. Hyperliquid Market Making (OHLCV-driven, SDK optional) --------------

class HyperliquidStrategy(BaseStrategy):
    agent_type = "hyperliquid_mm"
    strategy_name = "Hyperliquid Market Making"

    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        c = config
        self.sma_period = int(c.get("sma_period", 10))
        self.spread_pct = c.get("spread_pct", 0.01)
        self.order_size = c.get("order_size", 0.1)
        self.position_limit = c.get("position_limit", 1.0)

    def act(self, state, context):
        market_data = state.get("market_data", {})
        positions = context.get("positions", [])
        decision = self._hold()
        for symbol, data in market_data.items():
            closes = data.get("close_history", [])
            if "close" not in data or not closes:
                continue
            price = data.get("close")
            fair = _sma(closes, self.sma_period) if len(closes) >= self.sma_period else price
            bid, ask = fair * (1 - self.spread_pct / 2), fair * (1 + self.spread_pct / 2)
            pos = next((p for p in positions if p.symbol == symbol), None)
            size = pos.size if pos else 0
            if price <= bid and size < self.position_limit:
                return {"action": "BUY", "symbol": symbol, "size": self.order_size,
                        "reason": f"MARKET_MAKE_BUY (Price {price:.2f}<=Bid {bid:.2f})",
                        "exchange": "hyperliquid", "strategy_name": self.strategy_name}
            if price >= ask and size > -self.position_limit:
                return {"action": "SELL", "symbol": symbol, "size": self.order_size,
                        "reason": f"MARKET_MAKE_SELL (Price {price:.2f}>=Ask {ask:.2f})",
                        "exchange": "hyperliquid", "strategy_name": self.strategy_name}
            decision = self._hold(symbol, f"Quoting {symbol} | bid={bid:.2f} ask={ask:.2f}")
        return decision


# --- 7. Order Book Imbalance (live-only) ------------------------------------

class OrderBookStrategy(BaseStrategy):
    agent_type = "order_book"
    strategy_name = "Order Book Imbalance"

    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        c = config
        self.mode = c.get("mode", "cumulative")
        self.target_level = c.get("target_level", 5)
        self.depth_levels = c.get("depth_levels", 10)
        self.imbalance_threshold = c.get("imbalance_threshold", 1.5)
        self.min_volume = c.get("min_volume", 0.0)
        self.position_size = c.get("position_size", 0.1)
        self.profit_percentage = c.get("profit_percentage", 0.02)
        self.stop_loss_percentage = c.get("stop_loss_percentage", 0.01)

    def act(self, state, context):
        market_data = state.get("market_data", {})
        positions = context.get("positions", [])
        decision = self._hold(reason="No imbalance signal")
        for symbol, data in market_data.items():
            orderbook = data.get("orderbook")
            if not orderbook:
                continue
            pos = next((p for p in positions if p.symbol == symbol), None)
            if pos:
                price = data.get("close", 0)
                if price >= pos.entry_price * (1 + self.profit_percentage):
                    return self._sell(symbol, pos.size, f"TAKE_PROFIT (+{self.profit_percentage:.1%})")
                if price <= pos.entry_price * (1 - self.stop_loss_percentage):
                    return self._sell(symbol, pos.size, f"STOP_LOSS (-{self.stop_loss_percentage:.1%})")
            else:
                imb = self._imbalance(orderbook)
                if imb and imb["ratio"] >= self.imbalance_threshold:
                    return {"action": "BUY", "symbol": symbol, "size": self.position_size,
                            "reason": f"{self.mode.upper()}: Bid/Ask={imb['ratio']:.2f}",
                            "imbalance_ratio": imb["ratio"], "mode": self.mode,
                            "strategy_name": self.strategy_name}
        return decision

    def _imbalance(self, ob):
        bids, asks = ob.get("bids", []), ob.get("asks", [])
        if not bids or not asks:
            return None
        levels = min(self.depth_levels, len(bids), len(asks))
        if levels < 3:
            return None
        tb = sum(float(bids[i][1]) for i in range(levels))
        ta = sum(float(asks[i][1]) for i in range(levels))
        if ta == 0 or tb < self.min_volume:
            return None
        return {"ratio": tb / ta, "bid_volume": tb, "ask_volume": ta}

    def _sell(self, symbol, size, reason):
        return {"action": "SELL", "symbol": symbol, "size": size,
                "reason": reason, "strategy_name": self.strategy_name}


# --- 8. Arbitrage (live-only) -----------------------------------------------

class ArbitrageStrategy(BaseStrategy):
    agent_type = "arbitrage"
    strategy_name = "Exchange Arbitrage"

    def __init__(self, agent_id, config):
        super().__init__(agent_id, config)
        c = config
        self.min_spread_pct = c.get("min_spread_pct", 0.15)
        self.position_size = c.get("position_size", 0.05)
        self.max_hold_seconds = c.get("max_hold_seconds", 30)
        self.exchanges = c.get("exchanges", ["binance", "kraken", "coinbase"])

    def act(self, state, context):
        market_data = state.get("market_data", {})
        decision = self._hold(reason="No arbitrage opportunity")
        for symbol, data in market_data.items():
            if not isinstance(data, dict):
                continue
            best_bid = best_ask = None
            bid_ex = ask_ex = None
            for ex, pd_ in data.items():
                if isinstance(pd_, dict) and "bid" in pd_ and "ask" in pd_:
                    if best_bid is None or pd_["bid"] > best_bid:
                        best_bid, bid_ex = pd_["bid"], ex
                    if best_ask is None or pd_["ask"] < best_ask:
                        best_ask, ask_ex = pd_["ask"], ex
            if best_bid is None or best_ask is None:
                continue
            spread_pct = ((best_bid - best_ask) / best_ask) * 100
            if spread_pct > self.min_spread_pct:
                return {"action": "ARBITRAGE", "symbol": symbol, "size": self.position_size,
                        "reason": f"SPREAD_OPPORTUNITY ({spread_pct:.3f}%)",
                        "buy_exchange": ask_ex, "buy_price": best_ask,
                        "sell_exchange": bid_ex, "sell_price": best_bid,
                        "spread_pct": spread_pct, "strategy_name": self.strategy_name}
        return decision


STRATEGY_REGISTRY = {
    "momentum": MomentumStrategy,
    "mean_reversion": MeanReversionStrategy,
    "buy_the_dip": BuyTheDipStrategy,
    "market_making": MarketMakingStrategy,
    "box_wedge": BoxWedgeStrategy,
    "hyperliquid": HyperliquidStrategy,
    "order_book": OrderBookStrategy,
    "arbitrage": ArbitrageStrategy,
}


def build_strategy(agent_type: str, config: Dict[str, Any]):
    """Instantiate a strategy by its registry key."""
    if agent_type not in STRATEGY_REGISTRY:
        raise ValueError(f"Unknown crypto strategy: {agent_type}")
    return STRATEGY_REGISTRY[agent_type](f"{agent_type}_crypto", config)
