-- ============================================================================
-- AssetHero — prediction vertical tables (schema: assethero)
-- ============================================================================
-- Prediction-specific storage only. Runs, trades and backtest summaries reuse the
-- SHARED tables in sql/assethero_schema.sql (assethero.runs / trades /
-- backtest_summaries), tagged with vertical='prediction'. This file adds a
-- lightweight cache of resolved weather markets so backtests/predictions don't
-- re-hit the Gamma API for the same city/date.
--
--   Apply:  psql "$DATABASE_URL" -f sql/prediction_tables.sql
-- Safe to run repeatedly (CREATE TABLE IF NOT EXISTS).
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS assethero;

-- Cache of discovered/resolved Polymarket weather markets (per user).
CREATE TABLE IF NOT EXISTS assethero.prediction_weather_markets (
    id              SERIAL PRIMARY KEY,
    user_id         UUID REFERENCES assethero.users(user_id) ON DELETE CASCADE,
    market_id       VARCHAR(128) NOT NULL,          -- Gamma market id
    condition_id    VARCHAR(128),                   -- on-chain condition id
    clob_token_id   VARCHAR(128),                   -- YES token id (for price history)
    city            VARCHAR(64),
    market_date     DATE,                           -- calendar day the market resolves on
    question        TEXT,
    threshold_f     NUMERIC(8,2),                   -- parsed temperature bucket (°F)
    yes_price       NUMERIC(8,4),
    liquidity       NUMERIC(18,4),
    closed          BOOLEAN NOT NULL DEFAULT FALSE,
    resolution      NUMERIC(4,2),                   -- 1.0 YES / 0.0 NO / NULL unresolved
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, market_id)
);

CREATE INDEX IF NOT EXISTS idx_pred_wmkt_user  ON assethero.prediction_weather_markets(user_id);
CREATE INDEX IF NOT EXISTS idx_pred_wmkt_city  ON assethero.prediction_weather_markets(city, market_date);
CREATE INDEX IF NOT EXISTS idx_pred_wmkt_mkt   ON assethero.prediction_weather_markets(market_id);
