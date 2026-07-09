"""CCXT crypto market-data feed for the crypto vertical.

Fetches OHLCV / ticker / order-book from a CCXT-supported exchange. API keys
resolve through `engine.integrations.resolve(user_id, provider, field)` (per-user
encrypted keys with an env fallback), never `os.getenv` directly. Public
endpoints (OHLCV/ticker/order book) work without keys, so the feed degrades
gracefully to unauthenticated access.

`ccxt`, `numpy` and `pandas` are imported lazily inside methods so
`import engine.feeds.ccxt_feed` succeeds even when ccxt is not installed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Exchanges that map 1:1 to a ccxt id and an integrations provider key.
SUPPORTED_EXCHANGES = ["kraken", "okx", "binance", "bybit", "coinbase"]

# provider field -> ccxt config key
_FIELD_MAP = {
    "api_key": "apiKey",
    "api_secret": "secret",
    "passphrase": "password",
}


class CCXTFeed:
    """Thin CCXT wrapper returning pandas DataFrames for OHLCV."""

    def __init__(self, exchange: str = "kraken", user_id: Optional[str] = None):
        self.exchange_id = (exchange or "kraken").lower()
        self.user_id = user_id
        self._exchange = None  # lazily constructed ccxt client

    # -- connection ---------------------------------------------------------
    def _resolve_credentials(self) -> Dict[str, str]:
        """Resolve exchange creds via the integrations registry (no os.getenv)."""
        from engine.integrations import resolve
        cfg: Dict[str, str] = {}
        for field, ccxt_key in _FIELD_MAP.items():
            val = resolve(self.user_id, self.exchange_id, field)
            if val:
                cfg[ccxt_key] = val
        return cfg

    def client(self):
        """Build (and cache) the ccxt exchange client. Lazy ccxt import."""
        if self._exchange is not None:
            return self._exchange
        import ccxt
        if not hasattr(ccxt, self.exchange_id):
            raise ValueError(f"Unknown ccxt exchange: {self.exchange_id}")
        config: Dict[str, Any] = {"enableRateLimit": True}
        config.update(self._resolve_credentials())
        self._exchange = getattr(ccxt, self.exchange_id)(config)
        return self._exchange

    # -- data ---------------------------------------------------------------
    def fetch_ohlcv(self, symbol: str, timeframe: str = "1m", limit: int = 500):
        """Return OHLCV as a pandas DataFrame with seasonality columns.

        Falls back to public (keyless) access if authenticated access fails.
        """
        import numpy as np
        import pandas as pd
        exchange = self.client()
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:  # noqa: BLE001 — retry as public
            msg = str(e)
            if any(x in msg for x in ("Invalid API-key", "permission", "400",
                                      "10002", "timestamp", "recv_window", "auth")):
                logger.warning("CCXT auth failed (%s); retrying public", type(e).__name__)
                exchange.apiKey = None
                exchange.secret = None
                exchange.password = None
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            else:
                raise
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if df.empty:
            return df
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.dayofweek
        df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24)
        df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24)
        df["day_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7)
        df["day_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7)
        return df

    def fetch_ticker(self, symbol: str) -> Dict[str, Any]:
        return self.client().fetch_ticker(symbol)

    def fetch_orderbook(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        return self.client().fetch_order_book(symbol, limit=limit)


def timeframe_to_minutes(timeframe: str) -> int:
    """Convert a ccxt timeframe string (1m/5m/1h/1d) to minutes."""
    tf = timeframe.strip().lower()
    if tf.endswith("m"):
        return int(tf[:-1])
    if tf.endswith("h"):
        return int(tf[:-1]) * 60
    if tf.endswith("d"):
        return int(tf[:-1]) * 1440
    return 1
