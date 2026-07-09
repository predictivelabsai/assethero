"""Static FX / macro configuration — currency pairs, macro event categories and
RSS news sources. Ported from macrohero's config.yaml so no YAML file or runtime
config loader is needed. Pure data + tiny lookup helpers (no heavy imports)."""
from __future__ import annotations

# --- currency pairs ---------------------------------------------------------
# yf_ticker is the Yahoo Finance symbol (yfinance appends "=X" for FX spot).
CURRENCY_PAIRS = [
    {"pair": "EURUSD", "base": "EUR", "quote": "USD", "yf_ticker": "EURUSD=X"},
    {"pair": "GBPUSD", "base": "GBP", "quote": "USD", "yf_ticker": "GBPUSD=X"},
    {"pair": "USDJPY", "base": "USD", "quote": "JPY", "yf_ticker": "USDJPY=X"},
    {"pair": "USDCHF", "base": "USD", "quote": "CHF", "yf_ticker": "USDCHF=X"},
    {"pair": "AUDUSD", "base": "AUD", "quote": "USD", "yf_ticker": "AUDUSD=X"},
    {"pair": "USDCAD", "base": "USD", "quote": "CAD", "yf_ticker": "USDCAD=X"},
]

SUPPORTED_PAIRS = [p["pair"] for p in CURRENCY_PAIRS]
SUPPORTED_PERIODS = ["3mo", "6mo", "1y", "2y"]

# --- macro event categories (keyword classifier + UI chips) -----------------
EVENT_CATEGORIES = [
    {"name": "Central Bank", "slug": "central-bank", "icon": "landmark", "color": "#ef4444",
     "display_order": 1,
     "keywords": ["central bank", "fed", "ecb", "boe", "boj", "interest rate", "monetary policy",
                  "rate decision", "quantitative", "tightening", "dovish", "hawkish", "fomc",
                  "rate cut", "rate hike"]},
    {"name": "Earnings", "slug": "earnings", "icon": "bar-chart-2", "color": "#3b82f6",
     "display_order": 2,
     "keywords": ["earnings", "revenue", "profit", "quarterly results", "financial results",
                  "eps", "guidance", "beat estimates", "missed estimates"]},
    {"name": "GDP & Growth", "slug": "gdp", "icon": "trending-up", "color": "#10b981",
     "display_order": 3,
     "keywords": ["gdp", "growth", "recession", "economic expansion", "contraction", "pmi",
                  "manufacturing", "services pmi", "economic outlook"]},
    {"name": "Trade & Tariffs", "slug": "trade", "icon": "globe", "color": "#f59e0b",
     "display_order": 4,
     "keywords": ["trade", "tariff", "import", "export", "sanctions", "trade war", "trade deal",
                  "trade deficit", "trade surplus", "protectionism"]},
    {"name": "Employment", "slug": "employment", "icon": "users", "color": "#8b5cf6",
     "display_order": 5,
     "keywords": ["employment", "jobs", "unemployment", "nonfarm", "payroll", "labor",
                  "jobless claims", "hiring", "layoffs", "wage growth"]},
    {"name": "Inflation", "slug": "inflation", "icon": "flame", "color": "#ec4899",
     "display_order": 6,
     "keywords": ["inflation", "cpi", "ppi", "deflation", "price index", "consumer prices",
                  "core inflation", "disinflation", "stagflation"]},
    {"name": "Geopolitical", "slug": "geopolitical", "icon": "shield", "color": "#dc2626",
     "display_order": 7,
     "keywords": ["geopolitical", "war", "conflict", "sanctions", "nato", "military", "invasion",
                  "election", "regime", "coup", "diplomacy"]},
]

CATEGORY_SLUGS = [c["slug"] for c in EVENT_CATEGORIES]

REGIONS = [
    {"name": "US", "currencies": ["USD"]},
    {"name": "Europe", "currencies": ["EUR", "GBP", "CHF"]},
    {"name": "Asia-Pacific", "currencies": ["JPY", "AUD", "CNY"]},
    {"name": "Americas", "currencies": ["CAD", "MXN", "BRL"]},
]

# --- RSS news sources --------------------------------------------------------
RSS_SOURCES = [
    {"name": "Financial Times", "domain": "ft.com",
     "rss_url": "https://www.ft.com/rss/home", "language": "en"},
    {"name": "Bloomberg", "domain": "bloomberg.com",
     "rss_url": "https://feeds.bloomberg.com/markets/news.rss", "language": "en"},
    {"name": "Wall Street Journal", "domain": "wsj.com",
     "rss_url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml", "language": "en"},
    {"name": "Reuters", "domain": "reuters.com",
     "rss_url": "https://www.reutersagency.com/feed/", "language": "en"},
    {"name": "CNBC", "domain": "cnbc.com",
     "rss_url": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147",
     "language": "en"},
]

# --- LLM settings (xAI Grok) ------------------------------------------------
LLM = {
    "model": "grok-3",
    "temperature": 0.4,
    "max_tokens": 2000,
    "enrichment_model": "grok-3",
    "enrichment_temperature": 0.1,
}


def pair_config(pair: str) -> dict | None:
    """Return the config dict for a pair name (case-insensitive, '/' tolerant)."""
    key = (pair or "").upper().replace("/", "")
    return next((p for p in CURRENCY_PAIRS if p["pair"] == key), None)


def yf_ticker(pair: str) -> str:
    """Yahoo Finance ticker for a pair (falls back to ``<PAIR>=X``)."""
    cfg = pair_config(pair)
    return cfg["yf_ticker"] if cfg else f"{(pair or '').upper().replace('/', '')}=X"


def category(slug: str) -> dict | None:
    return next((c for c in EVENT_CATEGORIES if c["slug"] == slug), None)
