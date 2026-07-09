"""Per-user integrations — encrypted API keys for brokers, exchanges, wallets
and data providers, surfaced on the Admin / Integrations page.

Each provider's secret fields are stored as ONE Fernet-encrypted JSON blob per
(user, provider) in assethero.user_integrations, so no plaintext key hits disk.
Feeds/brokers resolve a value with `resolve(user_id, provider, field)`, which
falls back to the process env var when the user hasn't set their own key.

Registry only — actual connectivity lives in engine/feeds/* and engine/brokers/*.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

# --- provider registry ------------------------------------------------------
# field = (key, label, is_secret, env_fallback)
# A provider belongs to a category (trading|data) and a vertical (for grouping).

class Field:
    __slots__ = ("key", "label", "secret", "env")
    def __init__(self, key, label, secret=True, env=None):
        self.key, self.label, self.secret, self.env = key, label, secret, env


class Provider:
    __slots__ = ("key", "name", "category", "vertical", "fields", "help")
    def __init__(self, key, name, category, vertical, fields, help=""):
        self.key, self.name, self.category = key, name, category
        self.vertical, self.fields, self.help = vertical, fields, help


PROVIDERS: list[Provider] = [
    # ---- Trading platforms (brokers / exchanges / wallets) ----
    Provider("alpaca", "Alpaca", "trading", "equities", [
        Field("api_key", "Paper API key", True, "ALPACA_PAPER_API_KEY"),
        Field("api_secret", "Paper secret key", True, "ALPACA_PAPER_SECRET_KEY"),
    ], "US equities & ETFs — paper trading API."),
    Provider("kraken", "Kraken", "trading", "crypto", [
        Field("api_key", "API key", True, "KRAKEN_API_KEY"),
        Field("api_secret", "API secret", True, "KRAKEN_API_SECRET"),
    ], "Crypto spot (default exchange)."),
    Provider("okx", "OKX", "trading", "crypto", [
        Field("api_key", "API key", True, "OKX_API_KEY"),
        Field("api_secret", "API secret", True, "OKX_API_SECRET"),
        Field("passphrase", "Passphrase", True, "OKX_PASSPHRASE"),
    ], "Crypto spot."),
    Provider("binance", "Binance", "trading", "crypto", [
        Field("api_key", "API key", True, "BINANCE_API_KEY"),
        Field("api_secret", "API secret", True, "BINANCE_API_SECRET"),
    ], "Crypto spot."),
    Provider("bybit", "Bybit", "trading", "crypto", [
        Field("api_key", "API key", True, "BYBIT_API_KEY"),
        Field("api_secret", "API secret", True, "BYBIT_API_SECRET"),
    ], "Crypto spot."),
    Provider("coinbase", "Coinbase", "trading", "crypto", [
        Field("api_key", "API key", True, "COINBASE_API_KEY"),
        Field("api_secret", "API secret", True, "COINBASE_API_SECRET"),
        Field("passphrase", "Passphrase", True, "COINBASE_PASSPHRASE"),
    ], "Crypto spot."),
    Provider("hyperliquid", "Hyperliquid", "trading", "crypto", [
        Field("account_address", "Account address", False, "HYPERLIQUID_ACCOUNT_ADDRESS"),
        Field("secret_key", "Secret key", True, "HYPERLIQUID_SECRET_KEY"),
        Field("testnet", "Testnet (true/false)", False, "HYPERLIQUID_TESTNET"),
    ], "Crypto perpetuals (market-making)."),
    Provider("polymarket", "Polymarket", "trading", "prediction", [
        Field("wallet_private_key", "Polygon wallet private key", True, "POLYMARKET_WALLET_PRIVATE_KEY"),
        Field("polygon_rpc_url", "Polygon RPC URL (optional)", False, "POLYGON_RPC_URL"),
    ], "Prediction markets — proxy + CLOB creds auto-derived from the wallet key."),

    # ---- Data sources ----
    Provider("massive", "Massive / Polygon", "data", "equities", [
        Field("api_key", "API key", True, "MASSIVE_API_KEY"),
    ], "Equities market data (Polygon-compatible)."),
    Provider("eodhd", "EODHD", "data", "fx", [
        Field("api_key", "API key", True, "EODHD_API_KEY"),
    ], "Intraday + Treasury yield-curve data."),
    Provider("visual_crossing", "Visual Crossing", "data", "prediction", [
        Field("api_key", "API key", True, "VISUAL_CROSSING_API_KEY"),
    ], "Weather data (primary) for prediction-market fair value."),
    Provider("tomorrowio", "Tomorrow.io", "data", "prediction", [
        Field("api_key", "API key", True, "TOMORROWIO_API_KEY"),
    ], "Weather forecast (secondary cross-check)."),
    Provider("tavily", "Tavily", "data", "fx", [
        Field("api_key", "API key", True, "TAVILY_API_KEY"),
    ], "Web / macro-news search."),
    Provider("xai", "xAI (Grok)", "data", "shared", [
        Field("api_key", "API key", True, "XAI_API_KEY"),
    ], "LLM for the AI assistant & research agents."),
    Provider("openai", "OpenAI", "data", "shared", [
        Field("api_key", "API key", True, "OPENAI_API_KEY"),
    ], "LLM (alternative provider)."),
    Provider("groq", "Groq", "data", "shared", [
        Field("api_key", "API key", True, "GROQ_API_KEY"),
    ], "LLM (fast inference, crypto decision engine)."),
]

PROVIDERS_BY_KEY = {p.key: p for p in PROVIDERS}
TRADING = [p for p in PROVIDERS if p.category == "trading"]
DATA = [p for p in PROVIDERS if p.category == "data"]


# --- storage ----------------------------------------------------------------

def _pool():
    from utils.db.db_pool import DatabasePool
    return DatabasePool()


def get_config(user_id: str, provider: str) -> dict:
    """Return the decrypted {field: value} dict for a user's provider ({} if unset)."""
    from sqlalchemy import text
    from engine.auth import decrypt_key
    with _pool().get_session() as s:
        row = s.execute(text("""
            SELECT config_enc FROM assethero.user_integrations
            WHERE user_id = :u AND provider = :p
        """), {"u": user_id, "p": provider}).fetchone()
    if not row or not row[0]:
        return {}
    enc = bytes(row[0]) if isinstance(row[0], memoryview) else row[0]
    try:
        return json.loads(decrypt_key(enc))
    except Exception:  # noqa: BLE001
        return {}


def save_config(user_id: str, provider: str, config: dict, enabled: bool = True) -> None:
    """Encrypt and upsert a provider config for a user. Empty values are dropped."""
    from sqlalchemy import text
    from engine.auth import encrypt_key
    prov = PROVIDERS_BY_KEY.get(provider)
    category = prov.category if prov else "trading"
    clean = {k: v for k, v in config.items() if v not in (None, "")}
    enc = encrypt_key(json.dumps(clean)) if clean else None
    with _pool().get_session() as s:
        s.execute(text("""
            INSERT INTO assethero.user_integrations (user_id, provider, category, config_enc, enabled)
            VALUES (:u, :p, :c, :e, :en)
            ON CONFLICT (user_id, provider) DO UPDATE
              SET config_enc = :e, enabled = :en, category = :c, status = 'unknown', updated_at = NOW()
        """), {"u": user_id, "p": provider, "c": category, "e": enc, "en": enabled})


def set_status(user_id: str, provider: str, status: str) -> None:
    from sqlalchemy import text
    with _pool().get_session() as s:
        s.execute(text("""
            UPDATE assethero.user_integrations
            SET status = :st, last_tested = :now WHERE user_id = :u AND provider = :p
        """), {"st": status, "now": datetime.now(timezone.utc), "u": user_id, "p": provider})


def summary(user_id: str) -> dict:
    """Per-provider display state (NO secret values): {provider: {enabled, status, configured}}."""
    from sqlalchemy import text
    out = {}
    with _pool().get_session() as s:
        rows = s.execute(text("""
            SELECT provider, enabled, status, (config_enc IS NOT NULL) AS configured
            FROM assethero.user_integrations WHERE user_id = :u
        """), {"u": user_id}).fetchall()
    for r in rows:
        out[r[0]] = {"enabled": r[1], "status": r[2], "configured": r[3]}
    return out


def resolve(user_id: Optional[str], provider: str, field: str) -> Optional[str]:
    """Resolve a field value: the user's stored key first, else the env fallback.

    Lets feeds/brokers work for logged-out/CLI (env) and per-user (DB) alike.
    """
    if user_id:
        val = get_config(user_id, provider).get(field)
        if val:
            return val
    prov = PROVIDERS_BY_KEY.get(provider)
    if prov:
        fdef = next((f for f in prov.fields if f.key == field), None)
        if fdef and fdef.env:
            return os.getenv(fdef.env)
    return None


def test_connection(user_id: str, provider: str) -> tuple[bool, str]:
    """Light credential check. Real network tests are added per-vertical; for now
    this validates that required secret fields are present (env or user)."""
    prov = PROVIDERS_BY_KEY.get(provider)
    if not prov:
        return False, "unknown provider"
    missing = [f.label for f in prov.fields
               if f.secret and not resolve(user_id, provider, f.key)]
    if missing:
        set_status(user_id, provider, "error")
        return False, "missing: " + ", ".join(missing)
    set_status(user_id, provider, "ok")
    return True, "keys present"
