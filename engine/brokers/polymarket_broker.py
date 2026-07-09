"""Polymarket broker — prediction-market data + read-only on-chain portfolio.

SCOPE: BACKTEST + PAPER only. Real order placement is deliberately **omitted** —
this broker exposes market discovery, price history, book simulation and a
read-only on-chain portfolio view, but no `create_order`/`post_order`.

Dependency policy: the Gamma / CLOB REST reads use `requests` (imported lazily);
the on-chain portfolio path uses `py_clob_client` + `web3`, also imported lazily
inside `get_portfolio` only. So `import engine.brokers.polymarket_broker` succeeds
with none of those installed.

Credentials come from the encrypted integrations layer — the wallet private key is
resolved via `engine.integrations.resolve(user_id, "polymarket", "wallet_private_key")`
and is never read from a plaintext constant or logged.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"
DATA_URL = "https://data-api.polymarket.com"


@dataclass
class Market:
    id: str
    question: str
    yes_price: float
    no_price: float
    liquidity: float
    volume: float
    created_at: str = ""
    end_date: str = ""
    condition_id: Optional[str] = None
    clob_token_ids: List[str] = field(default_factory=list)
    closed: bool = False


class PolymarketBroker:
    """Read/simulate-only Polymarket client for the prediction vertical."""

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self._clob = None
        self._proxy = None

    # --- low-level HTTP (requests lazy) -------------------------------------

    def _get(self, url: str, params: Optional[dict] = None) -> Any:
        import requests
        resp = requests.get(url, params=params, timeout=30,
                            headers={"Accept": "application/json"})
        resp.raise_for_status()
        return resp.json()

    # --- market discovery ---------------------------------------------------

    def _parse_market(self, d: Dict[str, Any]) -> Market:
        last = d.get("lastTradePrice")
        bb, ba = d.get("bestBid"), d.get("bestAsk")
        if last is not None:
            yes = float(last)
        elif bb is not None and ba is not None:
            yes = (float(bb) + float(ba)) / 2
        else:
            yes = 0.5
        tokens = d.get("clobTokenIds", [])
        if isinstance(tokens, str) and tokens.strip():
            try:
                tokens = json.loads(tokens)
            except Exception:  # noqa: BLE001
                tokens = []
        return Market(
            id=str(d.get("id", "")),
            question=d.get("question", ""),
            yes_price=yes,
            no_price=1.0 - yes,
            liquidity=float(d.get("liquidity", 0) or 0),
            volume=float(d.get("volume24h", 0) or 0),
            created_at=d.get("createdAt", "") or "",
            end_date=d.get("endDate", "") or "",
            condition_id=d.get("conditionId"),
            clob_token_ids=tokens or [],
            closed=bool(d.get("closed", False)),
        )

    def get_markets(self, search: Optional[str] = None, limit: int = 100,
                    active: bool = True, closed: bool = False) -> List[Market]:
        params = {"limit": limit, "sortBy": "volume",
                  "active": "true" if active else "false",
                  "closed": "true" if closed else "false"}
        if search:
            params["search"] = search
        try:
            data = self._get(f"{GAMMA_URL}/markets", params)
            rows = data if isinstance(data, list) else data.get("data", [])
            return [self._parse_market(m) for m in rows]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_markets failed: {e}")
            return []

    def gamma_search(self, q: str, status: str = "active", limit: int = 50) -> List[Market]:
        """Keyword search via the Gamma public-search endpoint."""
        try:
            data = self._get(f"{GAMMA_URL}/public-search",
                             {"q": q, "events_status": status, "limit_per_type": limit})
            out: List[Market] = []
            for event in data.get("events", []):
                for m in event.get("markets", []):
                    out.append(self._parse_market(m))
            for m in data.get("markets", []):
                out.append(self._parse_market(m))
            return out
        except Exception as e:  # noqa: BLE001
            logger.error(f"gamma_search '{q}' failed: {e}")
            return []

    def get_market_by_id(self, market_id: str) -> Optional[Market]:
        try:
            return self._parse_market(self._get(f"{GAMMA_URL}/markets/{market_id}"))
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_market_by_id {market_id} failed: {e}")
            return None

    def search_weather_markets(self, cities: Optional[List[str]] = None,
                               min_liquidity: float = 0.0,
                               max_price: float = 1.0) -> List[Market]:
        cities = cities or ["London", "New York", "Seoul"]
        out: List[Market] = []
        for city in cities:
            for m in self.get_markets(search=f"weather {city} temperature", limit=50):
                if m.liquidity >= min_liquidity and m.yes_price <= max_price:
                    out.append(m)
        return out

    def get_price_history(self, token_id: str) -> List[Dict[str, Any]]:
        """Historical CLOB prices for a token id (best-effort across endpoints)."""
        candidates = [
            (f"{CLOB_URL}/prices-history", {"market": token_id, "interval": "max"}),
            (f"{CLOB_URL}/prices-history", {"market": token_id}),
            (f"{GAMMA_URL}/prices-history", {"market": token_id}),
        ]
        for url, params in candidates:
            try:
                data = self._get(url, params)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    if "history" in data:
                        return data["history"]
                    if "prices" in data:
                        return data["prices"]
            except Exception:  # noqa: BLE001
                continue
        return []

    def get_order_book(self, token_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = self._get(f"{CLOB_URL}/book", {"token_id": token_id})
            bids = [{"price": float(b["price"]), "size": float(b["size"])}
                    for b in data.get("bids", [])]
            asks = [{"price": float(a["price"]), "size": float(a["size"])}
                    for a in data.get("asks", [])]
            best_bid = max((b["price"] for b in bids), default=0.0)
            best_ask = min((a["price"] for a in asks), default=1.0)
            return {"token_id": token_id, "bids": bids, "asks": asks,
                    "best_bid": best_bid, "best_ask": best_ask,
                    "mid_price": (best_bid + best_ask) / 2}
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_order_book {token_id} failed: {e}")
            return None

    def simulate_trade(self, amount: float, token_id: str) -> Dict[str, Any]:
        """Walk the ask side of the book to estimate fill price / slippage (no order)."""
        book = self.get_order_book(token_id)
        if not book:
            return {"error": f"No order book for {token_id}"}
        remaining, shares, spent = amount, 0.0, 0.0
        for ask in book["asks"]:
            value = ask["price"] * ask["size"]
            if remaining <= value:
                shares += remaining / ask["price"]
                spent += remaining
                remaining = 0
                break
            shares += ask["size"]
            spent += value
            remaining -= value
        vwap = spent / shares if shares > 0 else 0.0
        best_ask = book["best_ask"]
        slippage = (vwap - best_ask) / best_ask if best_ask > 0 else 0.0
        return {"token_id": token_id, "amount_requested": amount,
                "amount_executed": spent, "shares": shares, "vwap": vwap,
                "best_ask": best_ask, "slippage": slippage,
                "insufficient_liquidity": remaining > 0}

    # --- read-only on-chain portfolio (heavy deps lazy) ---------------------

    def _ensure_clob(self) -> bool:
        if self._clob is not None:
            return True
        from engine.integrations import resolve
        pk = resolve(self.user_id, "polymarket", "wallet_private_key")
        if not pk:
            return False
        try:
            from py_clob_client.client import ClobClient  # lazy
            signer = ClobClient(host=CLOB_URL, key=pk, chain_id=137)
            addr = signer.get_address()
            try:
                prof = self._get(f"{GAMMA_URL}/public-profile", {"address": addr})
                self._proxy = prof.get("proxyWallet")
            except Exception:  # noqa: BLE001
                self._proxy = None
            sig_type = 1 if self._proxy else 0
            self._clob = ClobClient(host=CLOB_URL, key=pk, chain_id=137,
                                    funder=self._proxy, signature_type=sig_type)
            creds = self._clob.create_or_derive_api_creds()
            self._clob.set_api_creds(creds)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Polymarket CLOB init failed: {e}")
            return False

    def get_portfolio(self) -> Dict[str, Any]:
        """Read-only on-chain USDC balance + open positions (no trading)."""
        if not self._ensure_clob():
            return {"error": "Polymarket wallet not configured. Add your Polygon "
                             "wallet private key on the Integrations page."}
        try:
            from py_clob_client.clob_types import BalanceAllowanceParams, AssetType  # lazy
            bal = self._clob.get_balance_allowance(
                BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
            usdc = float(bal.get("balance", 0)) / 1e6
            positions: List[Dict[str, Any]] = []
            if self._proxy:
                try:
                    raw = self._get(f"{DATA_URL}/positions", {"user": self._proxy})
                    for rp in raw or []:
                        positions.append({
                            "market": rp.get("title"),
                            "outcome": rp.get("outcome"),
                            "size": float(rp.get("size", 0) or 0),
                            "entry_price": float(rp.get("avgPrice", 0) or 0),
                            "current_price": float(rp.get("curPrice", 0) or 0),
                            "current_value": float(rp.get("currentValue", 0) or 0),
                            "pnl": float(rp.get("cashPnl", 0) or 0),
                        })
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"positions fetch failed: {e}")
            return {"balance": usdc, "positions": positions}
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_portfolio failed: {e}")
            return {"error": str(e)}
