"""Shared command / agent-shortcut registry for the in-app shell.

Every asset-class vertical surfaces the same quick commands: agent shortcuts
(Backtest, Validate, Reconcile, Paper Trade, Full Cycle) in the right AI rail,
and a main-navigation menu (Trades, Runs & Reports, …) in the left nav. Copied
from agui_app._HELP_CATEGORIES so the CLI, AG-UI chat and web UI stay in sync.

Clicking any item fills the assistant input (ahFill) so it can be run/edited.
"""
from __future__ import annotations

# (group, [(command, description), ...]) — agent orchestration shortcuts.
AGENT_SHORTCUTS = [
    ("Backtest", [
        ("agent:backtest lookback:1m", "1-month backtest"),
        ("agent:backtest symbols:AAPL,TSLA", "custom symbols"),
        ("agent:backtest hours:extended", "pre/after-market"),
        ("agent:backtest intraday_exit:true", "5-min TP/SL bars"),
        ("agent:backtest pdt:false", "disable PDT rule"),
    ]),
    ("Validate", [
        ("agent:validate run-id:<uuid>", "validate a run"),
        ("agent:reconcile window:14d", "DB vs broker"),
    ]),
    ("Reconcile", [
        ("agent:reconcile window:7d", "7-day reconcile"),
        ("agent:reconcile window:30d", "30-day reconcile"),
    ]),
    ("Paper Trade", [
        ("agent:paper duration:7d", "paper trade 7 days"),
        ("agent:paper symbols:AAPL,MSFT", "custom symbols"),
        ("agent:paper poll:60", "60-second poll"),
        ("agent:paper hours:extended", "extended hours"),
        ("agent:stop", "stop paper trading"),
    ]),
    ("Full Cycle", [
        ("agent:full lookback:1m duration:1m", "backtest + validate + paper"),
        ("agent:full lookback:3m duration:7d", "3-month + 7-day paper"),
    ]),
]

# (group, [(command, description), ...]) — data / reporting navigation.
MAIN_NAV = [
    ("Trades", [
        ("trades:backtest", "backtest trades"),
        ("trades:paper", "paper trades"),
        ("trades:all", "all types + accounts"),
        ("trades:backtest slug:btd", "filter by slug"),
        ("trades:paper run-id:<uuid>", "specific run"),
    ]),
    ("Runs & Reports", [
        ("runs:backtest", "backtest runs"),
        ("runs:paper", "paper runs"),
        ("report:backtest", "backtest summary"),
        ("report:paper", "paper summary"),
        ("report run-id:<uuid>", "single run detail"),
    ]),
    ("Rankings & P&L", [
        ("top:backtest", "rank backtest strategies"),
        ("top:paper", "rank paper strategies"),
        ("top:all", "all types + accounts"),
        ("pnl run-id:<uuid>", "P&L breakdown"),
    ]),
    ("Monitor", [
        ("positions", "broker positions"),
        ("agent:status", "agent states"),
        ("agent:logs", "log tail"),
        ("agent:stop", "stop background task"),
    ]),
    ("Research", [
        ("load:AAPL", "quote + inline chart"),
        ("load:TSLA period:1y", "custom period"),
        ("news:TSLA", "company news"),
        ("price:AAPL", "quote"),
        ("profile:MSFT", "company profile"),
        ("analysts:GOOGL", "analyst ratings"),
        ("financials:AAPL", "income & balance sheet"),
        ("valuation:AAPL,MSFT", "valuation comparison"),
        ("movers", "top gainers & losers"),
        ("chart:AAPL period:1y", "chart"),
    ]),
    ("Charts & Equity", [
        ("equity", "latest run equity curve"),
        ("equity backtest", "latest backtest equity"),
        ("equity paper", "latest paper equity"),
        ("equity paper btd", "paper + slug"),
    ]),
    ("Accounts", [
        ("accounts", "list linked accounts"),
        ("account:add <KEY> <SECRET>", "add new account"),
        ("account:switch <num>", "switch active account"),
    ]),
    ("Options", [
        ("hours:extended", "pre/after-market hours"),
        ("pdt:false", "disable PDT rule"),
        ("intraday_exit:true", "intraday TP/SL exits"),
    ]),
]
