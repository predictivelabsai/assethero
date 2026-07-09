"""Hyperliquid broker — read-only info + guarded (paper-only) execution.

Wraps the Hyperliquid Python SDK for the crypto vertical's market-making
strategy. Scope is BACKTEST + PAPER only: live order placement is guarded
behind `allow_live=True` and raises by default.

Credentials resolve via `engine.integrations.resolve(user_id, "hyperliquid", ...)`
(account_address / secret_key / testnet). The `hyperliquid` SDK is imported
lazily so `import engine.brokers.hyperliquid_broker` works without it installed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class LiveTradingDisabled(RuntimeError):
    """Raised when live order placement is attempted while guarded off."""


class HyperliquidBroker:
    """Read-only Hyperliquid info client with guarded paper execution."""

    def __init__(self, user_id: Optional[str] = None, allow_live: bool = False):
        self.user_id = user_id
        self.allow_live = allow_live
        self._info = None
        self._exchange = None

    # -- credential resolution ---------------------------------------------
    def _cred(self, field: str) -> Optional[str]:
        from engine.integrations import resolve
        return resolve(self.user_id, "hyperliquid", field)

    def _is_testnet(self) -> bool:
        return str(self._cred("testnet") or "").lower() == "true"

    def info(self):
        """Return (and cache) a read-only Hyperliquid Info client. Lazy import."""
        if self._info is not None:
            return self._info
        from hyperliquid.info import Info
        from hyperliquid.utils import constants
        api_url = constants.TESTNET_API_URL if self._is_testnet() else constants.MAINNET_API_URL
        self._info = Info(api_url, skip_ws=True)
        return self._info

    def get_mid_price(self, coin: str = "BTC") -> Optional[float]:
        try:
            mids = self.info().all_mids()
            return float(mids[coin]) if coin in mids else None
        except Exception as e:  # noqa: BLE001
            logger.warning("hyperliquid mid price failed for %s: %s", coin, e)
            return None

    def user_state(self, address: Optional[str] = None) -> Optional[Dict[str, Any]]:
        address = address or self._cred("account_address")
        if not address:
            return None
        try:
            return self.info().user_state(address)
        except Exception as e:  # noqa: BLE001
            logger.warning("hyperliquid user_state failed: %s", e)
            return None

    # -- order placement (guarded) -----------------------------------------
    def submit_order(self, coin: str, is_buy: bool, size: float, price: float,
                     paper: bool = True) -> Dict[str, Any]:
        if paper:
            return {
                "status": "filled", "paper": True, "coin": coin,
                "side": "buy" if is_buy else "sell", "size": size, "price": price,
            }
        if not self.allow_live:
            raise LiveTradingDisabled(
                "Live Hyperliquid order placement is disabled in this build "
                "(backtest + paper only)."
            )
        raise LiveTradingDisabled("Live execution path is not wired.")
