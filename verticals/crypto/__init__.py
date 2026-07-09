"""Crypto vertical — multi-exchange backtesting & paper trading (CCXT +
Hyperliquid) with an RL hyperparameter tuner. Ported from rl-agent-swarm.

Public surface mirrors verticals/equities: import `routes` and call
`routes.register(app, rt, current_user)`. Routes also expose module-level
`NAV`, `RAIL_CHIPS` and `SHORTCUTS`.
"""
