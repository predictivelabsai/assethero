"""Prediction vertical — Polymarket weather-edge backtesting & paper trading.

Scope is BACKTEST + PAPER only; real order placement is intentionally omitted.
Reuses the shared engine (`engine.brokers.polymarket_broker`,
`engine.feeds.visualcrossing_feed`, `engine.feeds.tomorrowio_feed`) and persists to
the shared assethero tables tagged with vertical='prediction'.
"""
