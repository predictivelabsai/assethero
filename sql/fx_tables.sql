-- FX / Macro vertical tables (schema: assethero)
-- Ported from macrohero's macro-news model. FX backtests reuse the shared
-- assethero.runs / assethero.backtest_summaries / assethero.trades tables
-- (with vertical = 'fx'); only the macro-news pipeline needs new tables here.
--
-- Apply after sql/assethero_schema.sql. All statements are idempotent.

CREATE SCHEMA IF NOT EXISTS assethero;

-- News sources (RSS feeds).
CREATE TABLE IF NOT EXISTS assethero.sources (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(255) NOT NULL,
    domain      VARCHAR(255) NOT NULL UNIQUE,
    rss_url     TEXT,
    language    VARCHAR(10) NOT NULL DEFAULT 'en',
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Macro event categories (central bank, inflation, employment, …).
CREATE TABLE IF NOT EXISTS assethero.event_categories (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(128) NOT NULL UNIQUE,
    slug          VARCHAR(128) NOT NULL UNIQUE,
    icon          VARCHAR(64),
    color         VARCHAR(32),
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Macro news articles. user_id scopes a user's refreshed articles; NULL rows
-- are treated as shared (visible to everyone).
CREATE TABLE IF NOT EXISTS assethero.macro_news (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES assethero.users(user_id) ON DELETE SET NULL,
    source_id           UUID REFERENCES assethero.sources(id) ON DELETE SET NULL,
    url                 TEXT NOT NULL UNIQUE,
    title               TEXT NOT NULL,
    summary             TEXT,
    full_text           TEXT,
    author              VARCHAR(512),
    published_at        TIMESTAMPTZ,
    scraped_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    language            VARCHAR(10) DEFAULT 'en',
    word_count          INTEGER,
    region              VARCHAR(64),
    currency_tag        VARCHAR(16),
    event_category      VARCHAR(128),
    market_reasoning    TEXT,
    predicted_direction VARCHAR(10),
    predicted_magnitude REAL,
    model_used          VARCHAR(128),
    enriched_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_macro_news_created   ON assethero.macro_news(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_macro_news_user      ON assethero.macro_news(user_id);
CREATE INDEX IF NOT EXISTS idx_macro_news_currency  ON assethero.macro_news(currency_tag);
CREATE INDEX IF NOT EXISTS idx_macro_news_category  ON assethero.macro_news(event_category);
CREATE INDEX IF NOT EXISTS idx_macro_news_magnitude ON assethero.macro_news(predicted_magnitude);

-- Article <-> category junction (many-to-many).
CREATE TABLE IF NOT EXISTS assethero.news_categories (
    news_id         UUID NOT NULL REFERENCES assethero.macro_news(id) ON DELETE CASCADE,
    category_id     UUID NOT NULL REFERENCES assethero.event_categories(id) ON DELETE CASCADE,
    relevance_score REAL DEFAULT 1.0,
    PRIMARY KEY (news_id, category_id)
);
CREATE INDEX IF NOT EXISTS idx_news_categories_cat ON assethero.news_categories(category_id);
