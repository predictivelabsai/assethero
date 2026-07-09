-- Crypto vertical tables (schema: assethero)
-- ---------------------------------------------------------------------------
-- Runs, trades and backtest summaries REUSE the shared assethero.runs /
-- assethero.trades / assethero.backtest_summaries tables (vertical = 'crypto').
-- Only crypto-specific auxiliary tables live here:
--   * crypto_parameter_memory  — aggregated per-parameter performance for the
--                                 RL hyperparameter tuner (ported from
--                                 rl_agents.parameter_memory).
--   * crypto_portfolio_state   — periodic portfolio snapshots for the paper
--                                 sessions / portfolio supervisor (ported from
--                                 rl_agents.portfolio_state).
-- All tables carry user_id UUID (data isolation) + created_at.
-- Idempotent: safe to run repeatedly.
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS assethero;

-- Aggregated parameter performance (what parameter values made money).
CREATE TABLE IF NOT EXISTS assethero.crypto_parameter_memory (
    id             SERIAL PRIMARY KEY,
    user_id        UUID REFERENCES assethero.users(user_id) ON DELETE CASCADE,
    agent_type     VARCHAR(48) NOT NULL,          -- momentum|mean_reversion|...
    exchange       VARCHAR(32) NOT NULL,          -- kraken|okx|binance|...
    symbol         VARCHAR(32),
    param_name     VARCHAR(48) NOT NULL,
    param_value    NUMERIC(18,8) NOT NULL,
    total_trades   INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    total_pnl      NUMERIC(18,8) NOT NULL DEFAULT 0,
    avg_pnl        NUMERIC(18,8) NOT NULL DEFAULT 0,
    win_rate       NUMERIC(8,4)  NOT NULL DEFAULT 0,  -- 0..1
    last_updated   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, agent_type, exchange, symbol, param_name, param_value)
);
CREATE INDEX IF NOT EXISTS idx_crypto_param_memory_lookup
    ON assethero.crypto_parameter_memory (agent_type, exchange, param_name);
CREATE INDEX IF NOT EXISTS idx_crypto_param_memory_user
    ON assethero.crypto_parameter_memory (user_id);

-- Portfolio state snapshots for crypto paper sessions.
CREATE TABLE IF NOT EXISTS assethero.crypto_portfolio_state (
    id                    SERIAL PRIMARY KEY,
    user_id               UUID REFERENCES assethero.users(user_id) ON DELETE CASCADE,
    run_id                VARCHAR(64),                 -- optional link to assethero.runs
    snapshot_time         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    total_equity          NUMERIC(18,8) NOT NULL DEFAULT 0,
    total_cash            NUMERIC(18,8) NOT NULL DEFAULT 0,
    total_exposure        NUMERIC(18,8) NOT NULL DEFAULT 0,
    total_unrealized_pnl  NUMERIC(18,8) NOT NULL DEFAULT 0,
    total_realized_pnl    NUMERIC(18,8) NOT NULL DEFAULT 0,
    max_drawdown_pct      NUMERIC(10,4) NOT NULL DEFAULT 0,
    sharpe_ratio          NUMERIC(10,4),
    agent_allocations     JSONB,
    agent_parameters      JSONB,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_crypto_portfolio_state_user
    ON assethero.crypto_portfolio_state (user_id, snapshot_time DESC);
CREATE INDEX IF NOT EXISTS idx_crypto_portfolio_state_run
    ON assethero.crypto_portfolio_state (run_id);
