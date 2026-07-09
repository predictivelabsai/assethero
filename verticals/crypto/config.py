"""Crypto vertical configuration — agent registry, tunable ranges, defaults.

Ported from rl-agent-swarm `tasks/trading_engine.py` AGENT_CONFIGS. Each entry
holds the strategy's `default_config` and the `tunable_params` the RL tuner
(engine.backtest.tuner.RLHyperparameterTuner) may adjust.

No heavy imports here — this module is safe to import anywhere.
"""
from __future__ import annotations

# Exchanges (integrations provider keys) offered in the UI.
EXCHANGES = ["kraken", "okx", "binance", "bybit", "coinbase", "hyperliquid"]

# LLM providers usable by the (optional) crypto decision/assistant layer.
LLM_PROVIDERS = ["xai", "openai", "groq"]

DEFAULT_EXCHANGE = "kraken"
DEFAULT_SYMBOL = "BTC/USDC"
DEFAULT_TIMEFRAME = "1m"
DEFAULT_CAPITAL = 10000.0

# Full strategy registry (all 8). `live_only` strategies need real-time order
# book / cross-exchange feeds and are excluded from the backtest entrypoint.
AGENT_CONFIGS = {
    "momentum": {
        "label": "Momentum (MA cross + RSI/ADX)",
        "live_only": False,
        "tunable_params": {
            "fast_ma_period": {"min": 5, "max": 15, "step": 1},
            "slow_ma_period": {"min": 15, "max": 50, "step": 3},
            "adx_threshold": {"min": 10, "max": 30, "step": 2},
            "position_size": {"min": 0.03, "max": 0.12, "step": 0.01},
            "stop_loss_percentage": {"min": 0.008, "max": 0.03, "step": 0.002},
        },
        "default_config": {
            "fast_ma_period": 8, "slow_ma_period": 21, "rsi_period": 14,
            "rsi_upper": 75, "rsi_lower": 30, "adx_period": 14, "adx_threshold": 15,
            "position_size": 0.08, "profit_percentage": 0.02, "stop_loss_percentage": 0.015,
        },
    },
    "mean_reversion": {
        "label": "Mean Reversion (BB + RSI)",
        "live_only": False,
        "tunable_params": {
            "bb_period": {"min": 8, "max": 30, "step": 2},
            "bb_std": {"min": 1.2, "max": 2.5, "step": 0.1},
            "rsi_period": {"min": 7, "max": 21, "step": 1},
            "volume_mult": {"min": 0.5, "max": 1.5, "step": 0.1},
            "position_size": {"min": 0.02, "max": 0.1, "step": 0.01},
            "stop_loss_pct": {"min": 0.005, "max": 0.03, "step": 0.005},
        },
        "default_config": {
            "bb_period": 14, "bb_std": 1.8, "rsi_period": 14, "rsi_threshold": 35,
            "volume_mult": 0.8, "position_size": 0.05, "stop_loss_pct": 0.02,
        },
    },
    "buy_the_dip": {
        "label": "Buy The Dip",
        "live_only": False,
        "tunable_params": {
            "dip_percentage": {"min": 0.003, "max": 0.03, "step": 0.002},
            "profit_percentage": {"min": 0.005, "max": 0.03, "step": 0.005},
            "stop_loss_percentage": {"min": 0.005, "max": 0.03, "step": 0.005},
        },
        "default_config": {
            "sma_period": 14, "dip_percentage": 0.005, "profit_percentage": 0.015,
            "stop_loss_percentage": 0.015, "position_size": 0.08,
        },
    },
    "market_making": {
        "label": "Market Making (SMA fair value)",
        "live_only": False,
        "tunable_params": {
            "spread_pct": {"min": 0.001, "max": 0.01, "step": 0.001},
            "order_size": {"min": 0.01, "max": 1.0, "step": 0.05},
        },
        "default_config": {
            "sma_period": 5, "spread_pct": 0.004, "order_size": 0.1,
            "position_limit": 1.0,
        },
    },
    "box_wedge": {
        "label": "Box & Wedge breakout",
        "live_only": False,
        "tunable_params": {
            "volatility_threshold": {"min": 0.8, "max": 1.5, "step": 0.1},
            "risk_per_trade": {"min": 0.005, "max": 0.02, "step": 0.005},
            "scale_out_1r": {"min": 1.0, "max": 2.0, "step": 0.1},
            "scale_out_2r": {"min": 2.0, "max": 4.0, "step": 0.2},
        },
        "default_config": {
            "sma_period": 50, "ema_fast": 5, "ema_slow": 13, "box_lookback": 12,
            "volatility_threshold": 0.8, "wedge_lookback": 3, "risk_per_trade": 0.015,
            "scale_out_1r": 1.5, "scale_out_2r": 3.0, "runner_percentage": 0.25,
        },
    },
    "hyperliquid": {
        "label": "Hyperliquid Market Making (perps)",
        "live_only": False,
        "tunable_params": {
            "spread_pct": {"min": 0.002, "max": 0.02, "step": 0.002},
            "order_size": {"min": 0.01, "max": 1.0, "step": 0.05},
        },
        "default_config": {
            "sma_period": 10, "spread_pct": 0.01, "order_size": 0.1,
            "position_limit": 1.0,
        },
    },
    # --- live-only (excluded from backtest) --------------------------------
    "order_book": {
        "label": "Order Book Imbalance",
        "live_only": True,
        "tunable_params": {
            "imbalance_threshold": {"min": 1.2, "max": 3.0, "step": 0.1},
            "profit_percentage": {"min": 0.01, "max": 0.10, "step": 0.01},
            "stop_loss_percentage": {"min": 0.01, "max": 0.10, "step": 0.01},
            "position_size": {"min": 0.01, "max": 0.2, "step": 0.01},
        },
        "default_config": {
            "mode": "cumulative", "depth_levels": 10, "imbalance_threshold": 1.5,
            "position_size": 0.05, "profit_percentage": 0.02, "stop_loss_percentage": 0.10,
        },
    },
    "arbitrage": {
        "label": "Cross-Exchange Arbitrage",
        "live_only": True,
        "tunable_params": {
            "min_spread_pct": {"min": 0.05, "max": 0.5, "step": 0.05},
            "position_size": {"min": 0.01, "max": 0.2, "step": 0.01},
        },
        "default_config": {
            "min_spread_pct": 0.15, "position_size": 0.05, "max_hold_seconds": 30,
            "exchanges": ["binance", "kraken", "coinbase"],
        },
    },
}

# Strategies runnable in the backtest entrypoint (order_book/arbitrage excluded).
BACKTEST_AGENTS = [k for k, v in AGENT_CONFIGS.items() if not v["live_only"]]
# Strategies runnable in the paper loop (single-symbol OHLCV driven).
PAPER_AGENTS = [k for k, v in AGENT_CONFIGS.items() if not v["live_only"]]
ALL_AGENTS = list(AGENT_CONFIGS.keys())


def merged_config(agent_type: str, overrides: dict | None = None) -> dict:
    """default_config for an agent merged with caller overrides."""
    if agent_type not in AGENT_CONFIGS:
        raise ValueError(f"Unknown crypto agent: {agent_type}")
    cfg = dict(AGENT_CONFIGS[agent_type]["default_config"])
    if overrides:
        cfg.update({k: v for k, v in overrides.items() if v is not None})
    return cfg
