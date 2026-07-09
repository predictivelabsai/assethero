-- ============================================================================
-- AssetHero — consolidated schema (schema name: assethero)
-- ============================================================================
-- Single idempotent DDL for the multi-asset platform. Supersedes the legacy
-- piecemeal migrations (01–13, alpatrade schema). Safe to run repeatedly.
--
-- Layout:
--   Identity      users · user_accounts · password_reset_tokens
--   Trading       runs · backtest_summaries · trades · positions · pnl_summary · validations
--   Chat          chat_conversations · chat_messages
--
-- `runs.vertical` carries the asset class (equities / crypto / fx / prediction /
-- research) so one schema serves every vertical.
--   Apply:  psql "$DATABASE_URL" -f sql/assethero_schema.sql
--       or: python run_migration.py sql/assethero_schema.sql
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS assethero;

-- Shared updated_at trigger ---------------------------------------------------
CREATE OR REPLACE FUNCTION assethero.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Identity
-- ============================================================================

CREATE TABLE IF NOT EXISTS assethero.users (
    id             SERIAL PRIMARY KEY,
    user_id        UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    email          VARCHAR(255) UNIQUE NOT NULL,
    password_hash  VARCHAR(255),                 -- NULL for Google-only users
    google_id      VARCHAR(255) UNIQUE,          -- NULL for email-only users
    display_name   VARCHAR(255),
    is_admin       BOOLEAN NOT NULL DEFAULT FALSE,
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT users_auth_present CHECK (password_hash IS NOT NULL OR google_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_users_email      ON assethero.users(email);
CREATE INDEX IF NOT EXISTS idx_users_google_id  ON assethero.users(google_id);

DROP TRIGGER IF EXISTS trg_users_updated ON assethero.users;
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON assethero.users
    FOR EACH ROW EXECUTE FUNCTION assethero.set_updated_at();

-- Per-user broker accounts (encrypted keys live here, not on users).
CREATE TABLE IF NOT EXISTS assethero.user_accounts (
    id                     SERIAL PRIMARY KEY,
    account_id             UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
    user_id                UUID NOT NULL REFERENCES assethero.users(user_id) ON DELETE CASCADE,
    account_name           VARCHAR(255) NOT NULL DEFAULT 'Default Account',
    broker                 VARCHAR(32) NOT NULL DEFAULT 'alpaca',
    alpaca_api_key_enc     BYTEA,                 -- Fernet-encrypted
    alpaca_secret_key_enc  BYTEA,                 -- Fernet-encrypted
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_accounts_user_id ON assethero.user_accounts(user_id);

DROP TRIGGER IF EXISTS trg_user_accounts_updated ON assethero.user_accounts;
CREATE TRIGGER trg_user_accounts_updated BEFORE UPDATE ON assethero.user_accounts
    FOR EACH ROW EXECUTE FUNCTION assethero.set_updated_at();

CREATE TABLE IF NOT EXISTS assethero.password_reset_tokens (
    id          SERIAL PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES assethero.users(user_id) ON DELETE CASCADE,
    token       VARCHAR(128) UNIQUE NOT NULL,
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_prt_token ON assethero.password_reset_tokens(token);
CREATE INDEX IF NOT EXISTS idx_prt_user  ON assethero.password_reset_tokens(user_id);

-- ============================================================================
-- Trading
-- ============================================================================

-- One row per orchestrator run (backtest / paper / live), any vertical.
CREATE TABLE IF NOT EXISTS assethero.runs (
    id             SERIAL PRIMARY KEY,
    run_id         VARCHAR(64) UNIQUE NOT NULL,
    user_id        UUID REFERENCES assethero.users(user_id) ON DELETE SET NULL,
    account_id     UUID REFERENCES assethero.user_accounts(account_id) ON DELETE SET NULL,
    vertical       VARCHAR(32) NOT NULL DEFAULT 'equities',   -- equities|crypto|fx|prediction|research
    mode           VARCHAR(32) NOT NULL,                      -- backtest|paper|live|validate|...
    strategy       VARCHAR(64),
    strategy_slug  VARCHAR(128),
    symbols        TEXT[],
    status         VARCHAR(32) NOT NULL DEFAULT 'running',
    config         JSONB,
    results        JSONB,
    started_at     TIMESTAMPTZ,
    completed_at   TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_runs_run_id   ON assethero.runs(run_id);
CREATE INDEX IF NOT EXISTS idx_runs_status   ON assethero.runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_vertical ON assethero.runs(vertical);
CREATE INDEX IF NOT EXISTS idx_runs_user     ON assethero.runs(user_id);
CREATE INDEX IF NOT EXISTS idx_runs_slug     ON assethero.runs(strategy_slug);

-- One row per parameter variation tested in a backtest run.
CREATE TABLE IF NOT EXISTS assethero.backtest_summaries (
    id                 SERIAL PRIMARY KEY,
    run_id             VARCHAR(64) NOT NULL REFERENCES assethero.runs(run_id) ON DELETE CASCADE,
    user_id            UUID REFERENCES assethero.users(user_id) ON DELETE SET NULL,
    account_id         UUID REFERENCES assethero.user_accounts(account_id) ON DELETE SET NULL,
    variation_index    INTEGER NOT NULL DEFAULT 0,
    strategy_slug      VARCHAR(128),
    params             JSONB,
    total_return       NUMERIC(12,4),
    total_pnl          NUMERIC(12,4),
    win_rate           NUMERIC(8,4),
    total_trades       INTEGER,
    sharpe_ratio       NUMERIC(10,4),
    max_drawdown       NUMERIC(10,4),
    annualized_return  NUMERIC(10,4),
    is_best            BOOLEAN DEFAULT FALSE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_bs_run_id ON assethero.backtest_summaries(run_id);
CREATE INDEX IF NOT EXISTS idx_bs_slug   ON assethero.backtest_summaries(strategy_slug);

-- Unified trades table: backtest, paper, live.
CREATE TABLE IF NOT EXISTS assethero.trades (
    id             SERIAL PRIMARY KEY,
    run_id         VARCHAR(64) NOT NULL REFERENCES assethero.runs(run_id) ON DELETE CASCADE,
    user_id        UUID REFERENCES assethero.users(user_id) ON DELETE SET NULL,
    account_id     UUID REFERENCES assethero.user_accounts(account_id) ON DELETE SET NULL,
    trade_type     VARCHAR(16) NOT NULL,          -- backtest|paper|live
    strategy_slug  VARCHAR(128),
    symbol         VARCHAR(16),
    direction      VARCHAR(8),                    -- long|short
    shares         NUMERIC(18,8),
    entry_time     TIMESTAMPTZ,
    exit_time      TIMESTAMPTZ,
    entry_price    NUMERIC(18,8),
    exit_price     NUMERIC(18,8),
    target_price   NUMERIC(18,8),
    stop_price     NUMERIC(18,8),
    hit_target     BOOLEAN,
    hit_stop       BOOLEAN,
    pnl            NUMERIC(18,8),
    pnl_pct        NUMERIC(12,4),
    capital_after  NUMERIC(18,8),
    total_fees     NUMERIC(12,4) DEFAULT 0,
    dip_pct        NUMERIC(12,4),
    order_id       VARCHAR(64),
    reason         TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_trades_run_id   ON assethero.trades(run_id);
CREATE INDEX IF NOT EXISTS idx_trades_type      ON assethero.trades(trade_type);
CREATE INDEX IF NOT EXISTS idx_trades_symbol    ON assethero.trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_run_type  ON assethero.trades(run_id, trade_type);
CREATE INDEX IF NOT EXISTS idx_trades_slug      ON assethero.trades(strategy_slug);

-- Live/paper position state.
CREATE TABLE IF NOT EXISTS assethero.positions (
    id                  SERIAL PRIMARY KEY,
    run_id              VARCHAR(64) NOT NULL REFERENCES assethero.runs(run_id) ON DELETE CASCADE,
    user_id             UUID REFERENCES assethero.users(user_id) ON DELETE SET NULL,
    account_id          UUID REFERENCES assethero.user_accounts(account_id) ON DELETE SET NULL,
    symbol              VARCHAR(16) NOT NULL,
    side                VARCHAR(8) NOT NULL,      -- long|short
    shares              NUMERIC(18,8) NOT NULL DEFAULT 0,
    avg_entry_price     NUMERIC(18,8),
    current_price       NUMERIC(18,8),
    market_value        NUMERIC(18,4),
    unrealized_pnl      NUMERIC(18,4),
    unrealized_pnl_pct  NUMERIC(12,4),
    cost_basis          NUMERIC(18,4),
    status              VARCHAR(16) NOT NULL DEFAULT 'open',   -- open|closed
    opened_at           TIMESTAMPTZ,
    closed_at           TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_positions_run_symbol ON assethero.positions(run_id, symbol);
CREATE INDEX IF NOT EXISTS idx_positions_status     ON assethero.positions(status);

DROP TRIGGER IF EXISTS trg_positions_updated ON assethero.positions;
CREATE TRIGGER trg_positions_updated BEFORE UPDATE ON assethero.positions
    FOR EACH ROW EXECUTE FUNCTION assethero.set_updated_at();

-- Pre-aggregated P&L per run + symbol (NULL symbol = run-level totals).
CREATE TABLE IF NOT EXISTS assethero.pnl_summary (
    id                SERIAL PRIMARY KEY,
    run_id            VARCHAR(64) NOT NULL REFERENCES assethero.runs(run_id) ON DELETE CASCADE,
    user_id           UUID REFERENCES assethero.users(user_id) ON DELETE SET NULL,
    account_id        UUID REFERENCES assethero.user_accounts(account_id) ON DELETE SET NULL,
    symbol            VARCHAR(16),
    trade_count       INTEGER NOT NULL DEFAULT 0,
    win_count         INTEGER NOT NULL DEFAULT 0,
    loss_count        INTEGER NOT NULL DEFAULT 0,
    total_pnl         NUMERIC(18,4) NOT NULL DEFAULT 0,
    total_fees        NUMERIC(12,4) NOT NULL DEFAULT 0,
    avg_pnl           NUMERIC(18,4),
    avg_pnl_pct       NUMERIC(12,4),
    best_trade_pnl    NUMERIC(18,4),
    worst_trade_pnl   NUMERIC(18,4),
    total_return_pct  NUMERIC(12,4),
    win_rate          NUMERIC(8,4),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_pnl_summary_unique
    ON assethero.pnl_summary(run_id, COALESCE(symbol, '__TOTAL__'));

DROP TRIGGER IF EXISTS trg_pnl_summary_updated ON assethero.pnl_summary;
CREATE TRIGGER trg_pnl_summary_updated BEFORE UPDATE ON assethero.pnl_summary
    FOR EACH ROW EXECUTE FUNCTION assethero.set_updated_at();

-- Validator agent results.
CREATE TABLE IF NOT EXISTS assethero.validations (
    id                   SERIAL PRIMARY KEY,
    run_id               VARCHAR(64) NOT NULL REFERENCES assethero.runs(run_id) ON DELETE CASCADE,
    user_id              UUID REFERENCES assethero.users(user_id) ON DELETE SET NULL,
    source               VARCHAR(16),
    status               VARCHAR(16),
    total_checked        INTEGER,
    anomalies_found      INTEGER,
    anomalies_corrected  INTEGER,
    iterations_used      INTEGER,
    corrections          JSONB,
    suggestions          JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_validations_run_id ON assethero.validations(run_id);

-- ============================================================================
-- Chat (assistant persistence)
-- ============================================================================

CREATE TABLE IF NOT EXISTS assethero.chat_conversations (
    thread_id   UUID PRIMARY KEY,
    user_id     UUID REFERENCES assethero.users(user_id) ON DELETE CASCADE,
    vertical    VARCHAR(32) NOT NULL DEFAULT 'equities',
    title       VARCHAR(200) DEFAULT 'New chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_conv_user ON assethero.chat_conversations(user_id);

DROP TRIGGER IF EXISTS trg_chat_conv_updated ON assethero.chat_conversations;
CREATE TRIGGER trg_chat_conv_updated BEFORE UPDATE ON assethero.chat_conversations
    FOR EACH ROW EXECUTE FUNCTION assethero.set_updated_at();

CREATE TABLE IF NOT EXISTS assethero.chat_messages (
    id          BIGSERIAL PRIMARY KEY,
    thread_id   UUID NOT NULL REFERENCES assethero.chat_conversations(thread_id) ON DELETE CASCADE,
    message_id  UUID NOT NULL,
    role        VARCHAR(20) NOT NULL,            -- user|assistant
    content     TEXT NOT NULL DEFAULT '',
    metadata    JSONB,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_chat_msg_thread ON assethero.chat_messages(thread_id, created_at);
