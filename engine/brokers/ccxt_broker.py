"""CCXT crypto broker — read-only + simulated (paper) fills.

Scope is deliberately BACKTEST + PAPER only. Real/live order placement is
guarded behind `allow_live=True` and raises by default, mirroring the platform
policy of not wiring live crypto execution in this phase.

Keys resolve via `engine.integrations.resolve` (never os.getenv). `ccxt` is
imported lazily so `import engine.brokers.ccxt_broker` works without ccxt.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LiveTradingDisabled(RuntimeError):
    """Raised when live order placement is attempted while guarded off."""


class CCXTBroker:
    """Paper/read-only crypto broker over a CCXT exchange."""

    def __init__(self, exchange: str = "kraken", user_id: Optional[str] = None,
                 allow_live: bool = False):
        self.exchange_id = (exchange or "kraken").lower()
        self.user_id = user_id
        self.allow_live = allow_live
        self._feed = None

    def _feed_client(self):
        if self._feed is None:
            from engine.feeds.ccxt_feed import CCXTFeed
            self._feed = CCXTFeed(self.exchange_id, user_id=self.user_id)
        return self._feed

    # -- read-only market access -------------------------------------------
    def get_price(self, symbol: str) -> Optional[float]:
        try:
            t = self._feed_client().fetch_ticker(symbol)
            return float(t.get("last")) if t and t.get("last") is not None else None
        except Exception as e:  # noqa: BLE001
            logger.warning("get_price failed for %s: %s", symbol, e)
            return None

    def get_balance(self) -> Dict[str, Any]:
        """Fetch account balance (requires keys). Read-only."""
        try:
            return self._feed_client().client().fetch_balance()
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    # -- order placement (guarded) -----------------------------------------
    def submit_order(self, symbol: str, side: str, amount: float,
                     price: Optional[float] = None, order_type: str = "market",
                     paper: bool = True) -> Dict[str, Any]:
        """Place an order.

        With ``paper=True`` (default) this returns a simulated fill and never
        touches the exchange. A live order requires BOTH ``paper=False`` and the
        broker constructed with ``allow_live=True``; otherwise it raises
        ``LiveTradingDisabled``.
        """
        if paper:
            fill_price = price if price is not None else self.get_price(symbol)
            return {
                "status": "filled",
                "paper": True,
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": fill_price,
                "type": order_type,
            }
        if not self.allow_live:
            raise LiveTradingDisabled(
                "Live crypto order placement is disabled in this build "
                "(backtest + paper only)."
            )
        # Intentionally not implemented: live execution is out of scope.
        raise LiveTradingDisabled("Live execution path is not wired.")
