"""Macro-news pipeline for the FX vertical: RSS fetch -> scrape -> keyword
classify -> optional LLM enrich, persisted to the assethero schema.

Tables (see sql/fx_tables.sql): assethero.macro_news, assethero.sources,
assethero.event_categories, assethero.news_categories.

The macrohero background scheduler is intentionally omitted; instead
``refresh_news`` runs one fetch+classify(+enrich) pass on demand (the /fx/news
"Refresh" action). All heavy deps (feedparser, newspaper, langchain_openai) are
imported lazily so importing this module never requires them.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .config import EVENT_CATEGORIES, RSS_SOURCES

logger = logging.getLogger(__name__)


# --- DB helpers -------------------------------------------------------------

def _pool():
    from utils.db.db_pool import DatabasePool
    return DatabasePool()


def _exec(sql: str, params: dict | None = None):
    from sqlalchemy import text
    with _pool().get_session() as s:
        s.execute(text(sql), params or {})


def _fetchall(sql: str, params: dict | None = None) -> list[dict]:
    from sqlalchemy import text
    with _pool().get_session() as s:
        rows = s.execute(text(sql), params or {})
        cols = rows.keys()
        return [dict(zip(cols, r)) for r in rows.fetchall()]


def _fetchone(sql: str, params: dict | None = None) -> dict | None:
    rows = _fetchall(sql, params)
    return rows[0] if rows else None


# --- reference data (sources + categories) ----------------------------------

def seed_reference_data() -> None:
    """Idempotently upsert the configured sources + event categories."""
    for src in RSS_SOURCES:
        _exec("""
            INSERT INTO assethero.sources (name, domain, rss_url, language)
            VALUES (:name, :domain, :rss, :lang)
            ON CONFLICT (domain) DO UPDATE
              SET name = EXCLUDED.name, rss_url = EXCLUDED.rss_url
        """, {"name": src["name"], "domain": src["domain"],
              "rss": src["rss_url"], "lang": src.get("language", "en")})
    for cat in EVENT_CATEGORIES:
        _exec("""
            INSERT INTO assethero.event_categories (name, slug, icon, color, display_order)
            VALUES (:name, :slug, :icon, :color, :ord)
            ON CONFLICT (slug) DO UPDATE
              SET name = EXCLUDED.name, icon = EXCLUDED.icon, color = EXCLUDED.color,
                  display_order = EXCLUDED.display_order
        """, {"name": cat["name"], "slug": cat["slug"], "icon": cat["icon"],
              "color": cat["color"], "ord": cat["display_order"]})


# --- pipeline stages --------------------------------------------------------

def _parse_date(entry):
    from time import mktime
    for field in ("published_parsed", "updated_parsed"):
        val = getattr(entry, field, None) or (entry.get(field) if hasattr(entry, "get") else None)
        if val:
            try:
                return datetime.fromtimestamp(mktime(val), tz=timezone.utc)
            except Exception:  # noqa: BLE001
                pass
    return None


def fetch_rss(source: dict) -> list[dict]:
    """Parse one RSS source, returning article dicts for URLs not already stored."""
    import feedparser
    rss_url = source.get("rss_url")
    if not rss_url:
        return []
    try:
        feed = feedparser.parse(rss_url)
    except Exception as e:  # noqa: BLE001
        logger.error(f"RSS parse failed for {source['name']}: {e}")
        return []
    articles = []
    for entry in feed.entries:
        url = (entry.get("link") or "").strip()
        if not url:
            continue
        if _fetchone("SELECT id FROM assethero.macro_news WHERE url = :u", {"u": url}):
            continue
        articles.append({
            "url": url,
            "title": (entry.get("title") or "Untitled").strip(),
            "summary": (entry.get("summary") or "")[:1000].strip(),
            "author": (entry.get("author") or "").strip(),
            "published_at": _parse_date(entry),
            "language": source.get("language", "en"),
            "source_domain": source["domain"],
        })
    logger.info(f"RSS {source['name']}: {len(articles)} new / {len(feed.entries)} entries")
    return articles


def scrape_article(url: str) -> dict:
    """Fetch full article text via newspaper (newspaper4k). Best-effort."""
    try:
        from newspaper import Article
        a = Article(url)
        a.download()
        a.parse()
        return {"full_text": a.text, "author": ", ".join(a.authors) if a.authors else "",
                "word_count": len(a.text.split()) if a.text else 0}
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Scrape failed for {url}: {e}")
        return {"full_text": "", "author": "", "word_count": 0}


def classify_article(title: str, summary: str, full_text: str = "") -> list[dict]:
    """Keyword-match an article to event categories -> [{slug, relevance_score}]."""
    text_lower = f"{title} {summary} {full_text[:500]}".lower()
    matches = []
    for cat in EVENT_CATEGORIES:
        keywords = cat.get("keywords", [])
        hits = sum(1 for kw in keywords if kw.lower() in text_lower)
        if hits:
            relevance = min(1.0, hits / max(len(keywords) * 0.3, 1))
            matches.append({"slug": cat["slug"], "relevance_score": round(relevance, 2)})
    if not matches:
        matches.append({"slug": "geopolitical", "relevance_score": 0.1})
    return matches


def _save_categories(news_id, matches: list[dict]) -> None:
    for m in matches:
        try:
            _exec("""
                INSERT INTO assethero.news_categories (news_id, category_id, relevance_score)
                SELECT :nid, c.id, :score FROM assethero.event_categories c WHERE c.slug = :slug
                ON CONFLICT (news_id, category_id) DO NOTHING
            """, {"nid": news_id, "slug": m["slug"], "score": m["relevance_score"]})
        except Exception as e:  # noqa: BLE001
            logger.error(f"category link failed: {e}")


def enrich_article(article_id, title: str, text: str, source_name: str, xai_key: str) -> bool:
    """LLM enrich one article (region/currency/direction/magnitude/reasoning)."""
    import json
    if not xai_key or (not text and not title):
        return False
    from langchain_openai import ChatOpenAI
    from .config import LLM
    prompt = f"""Analyze this financial news article for macro-economic impact.

Title: {title}
Source: {source_name}
Text (excerpt): {text[:800]}

Respond with ONLY valid JSON, no other text:
{{"region": "<US|Europe|Asia-Pacific|Americas|Global>", "currency_tag": "<USD|EUR|GBP|JPY|CHF|AUD|CAD|null>", "event_category": "<central-bank|earnings|gdp|trade|employment|inflation|geopolitical|other>", "predicted_direction": "<up|down|neutral>", "predicted_magnitude": <float 0.0-5.0>, "market_reasoning": "<one paragraph explaining expected market impact>"}}"""
    try:
        llm = ChatOpenAI(api_key=xai_key, base_url="https://api.x.ai/v1",
                         model=LLM["enrichment_model"], temperature=LLM["enrichment_temperature"],
                         max_tokens=500)
        content = llm.invoke(prompt).content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        data = json.loads(content)
        currency = data.get("currency_tag")
        if currency == "null":
            currency = None
        direction = data.get("predicted_direction", "neutral")
        if direction not in ("up", "down", "neutral"):
            direction = "neutral"
        magnitude = max(0.0, min(5.0, float(data.get("predicted_magnitude", 0))))
        _exec("""
            UPDATE assethero.macro_news SET
                region = :region, currency_tag = :currency, event_category = :category,
                predicted_direction = :direction, predicted_magnitude = :magnitude,
                market_reasoning = :reasoning, model_used = :model, enriched_at = NOW()
            WHERE id = :id
        """, {"region": data.get("region", "Global"), "currency": currency,
              "category": data.get("event_category", "other"), "direction": direction,
              "magnitude": magnitude, "reasoning": data.get("market_reasoning", ""),
              "model": LLM["enrichment_model"], "id": article_id})
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"Enrichment failed for {title[:50]}: {e}")
        return False


# --- orchestrated refresh (manual action) -----------------------------------

def refresh_news(user_id: str | None = None, max_sources: int = 5,
                 scrape: bool = False, enrich_limit: int = 10, xai_key: str | None = None) -> dict:
    """One pass: seed refs, fetch RSS, insert new articles, classify, optionally
    scrape + LLM-enrich. Returns a summary dict. Safe to call repeatedly."""
    seed_reference_data()
    inserted, enriched = 0, 0
    errors: list[str] = []
    for src in RSS_SOURCES[:max_sources]:
        try:
            articles = fetch_rss(src)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{src['name']}: {e}")
            continue
        src_row = _fetchone("SELECT id FROM assethero.sources WHERE domain = :d",
                            {"d": src["domain"]})
        source_id = src_row["id"] if src_row else None
        for art in articles:
            full_text = ""
            if scrape:
                full_text = scrape_article(art["url"]).get("full_text", "")
            try:
                row = _fetchone("""
                    INSERT INTO assethero.macro_news
                        (source_id, user_id, url, title, summary, full_text, author,
                         published_at, language)
                    VALUES (:sid, :uid, :url, :title, :summary, :ft, :author, :pub, :lang)
                    ON CONFLICT (url) DO NOTHING
                    RETURNING id
                """, {"sid": source_id, "uid": user_id, "url": art["url"], "title": art["title"],
                      "summary": art["summary"], "ft": full_text or None, "author": art["author"],
                      "pub": art["published_at"], "lang": art["language"]})
            except Exception as e:  # noqa: BLE001
                errors.append(str(e))
                continue
            if not row:
                continue
            news_id = row["id"]
            inserted += 1
            _save_categories(news_id, classify_article(art["title"], art["summary"], full_text))
            if xai_key and enriched < enrich_limit:
                if enrich_article(news_id, art["title"], full_text or art["summary"],
                                  src["name"], xai_key):
                    enriched += 1
    return {"inserted": inserted, "enriched": enriched, "errors": errors[:5]}


# --- read queries -----------------------------------------------------------

def _user_scope(user_id: str | None):
    """SQL fragment + params to show a user's rows plus shared (NULL user) rows."""
    if user_id:
        return "(n.user_id = :uid OR n.user_id IS NULL)", {"uid": user_id}
    return "TRUE", {}


def recent_news(limit: int = 20, category: str = "", user_id: str | None = None) -> list[dict]:
    scope, params = _user_scope(user_id)
    params["limit"] = limit
    if category:
        params["slug"] = category
        return _fetchall(f"""
            SELECT n.id, n.title, n.url, n.author, n.published_at, n.region, n.currency_tag,
                   n.event_category, n.predicted_direction, n.predicted_magnitude,
                   n.market_reasoning, s.name AS source_name
            FROM assethero.macro_news n
            LEFT JOIN assethero.sources s ON s.id = n.source_id
            JOIN assethero.news_categories nc ON nc.news_id = n.id
            JOIN assethero.event_categories c ON c.id = nc.category_id AND c.slug = :slug
            WHERE {scope}
            ORDER BY n.created_at DESC LIMIT :limit
        """, params)
    return _fetchall(f"""
        SELECT n.id, n.title, n.url, n.author, n.published_at, n.region, n.currency_tag,
               n.event_category, n.predicted_direction, n.predicted_magnitude,
               n.market_reasoning, s.name AS source_name
        FROM assethero.macro_news n
        LEFT JOIN assethero.sources s ON s.id = n.source_id
        WHERE {scope}
        ORDER BY n.created_at DESC LIMIT :limit
    """, params)


def market_movers(hours: int = 24, limit: int = 10, user_id: str | None = None) -> list[dict]:
    scope, params = _user_scope(user_id)
    params.update({"hours": hours, "limit": limit})
    return _fetchall(f"""
        SELECT n.title, n.url, n.currency_tag, n.predicted_direction, n.predicted_magnitude,
               n.market_reasoning, s.name AS source_name
        FROM assethero.macro_news n
        LEFT JOIN assethero.sources s ON s.id = n.source_id
        WHERE {scope} AND n.created_at > NOW() - make_interval(hours => :hours)
          AND n.predicted_magnitude IS NOT NULL
        ORDER BY ABS(n.predicted_magnitude) DESC LIMIT :limit
    """, params)


def trending_categories(hours: int = 24, user_id: str | None = None) -> list[dict]:
    scope, params = _user_scope(user_id)
    params["hours"] = hours
    return _fetchall(f"""
        SELECT c.name, c.slug, c.color, c.icon, COUNT(nc.news_id) AS article_count
        FROM assethero.event_categories c
        JOIN assethero.news_categories nc ON nc.category_id = c.id
        JOIN assethero.macro_news n ON n.id = nc.news_id
        WHERE {scope} AND n.created_at > NOW() - make_interval(hours => :hours)
        GROUP BY c.id, c.name, c.slug, c.color, c.icon
        ORDER BY article_count DESC
    """, params)
