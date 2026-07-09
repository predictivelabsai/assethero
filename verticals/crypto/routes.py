"""Crypto vertical routes — mounted under /crypto/* by app.py.

Mirrors verticals/equities/routes.py: exposes `register(app, rt, current_user)`
plus module-level NAV, RAIL_CHIPS and SHORTCUTS. Rendered in the shared
house-style shell (engine.web.layout.page).

Everything crypto-specific (ccxt feeds, strategies, the backtest/paper engines)
is imported lazily inside handlers so `import verticals.crypto.routes` succeeds
even when ccxt / ta / hyperliquid are not installed. Handlers catch exceptions
and render a friendly error, exactly like equities.
"""
from __future__ import annotations

from fasthtml.common import (
    Div, Form, H2, H3, Input, Label, Option, P, Select, Table, Tbody, Td, Th,
    Thead, Tr, Button, NotStr,
)
from starlette.responses import RedirectResponse

from engine.web.layout import page

NAV = [
    ("Dashboard", "/crypto"),
    ("Backtest", "/crypto/backtest"),
    ("Runs", "/crypto/runs"),
]
RAIL_CHIPS = ["runs", "strategies", "exchanges", "help"]

# Module-level agent-shortcut menu for the crypto assistant (folded into the
# shared command menu by app.py). (group, [(command, description), ...]).
SHORTCUTS = [
    ("Backtest", [
        ("agent:backtest agent:momentum exchange:kraken", "momentum on Kraken"),
        ("agent:backtest agent:mean_reversion symbol:ETH/USDC", "mean reversion, ETH"),
        ("agent:backtest agent:buy_the_dip timeframe:5m", "buy-the-dip, 5m bars"),
        ("agent:backtest agent:box_wedge limit:2000", "box & wedge, 2000 candles"),
    ]),
    ("Paper Trade", [
        ("agent:paper agent:buy_the_dip exchange:kraken capital:1000", "paper buy-the-dip"),
        ("agent:paper agent:momentum symbol:BTC/USDC cycles:10", "paper momentum"),
        ("agent:paper agent:market_making exchange:okx", "paper market making"),
        ("agent:stop", "stop paper session"),
    ]),
    ("Strategies", [
        ("strategies", "list crypto strategies"),
        ("exchanges", "list supported exchanges"),
    ]),
    ("Runs & Reports", [
        ("runs", "recent crypto runs"),
        ("report run-id:<id>", "single run detail"),
    ]),
]


# --- data helpers -----------------------------------------------------------

def _recent_runs(limit=15, user_id=None):
    """Recent crypto runs from the shared assethero.runs table (best-effort)."""
    try:
        from sqlalchemy import text
        from utils.db.db_pool import DatabasePool
        clauses = ["r.vertical = 'crypto'"]
        bind = {"lim": limit}
        if user_id:
            clauses.append("r.user_id = :uid")
            bind["uid"] = user_id
        where = " AND ".join(clauses)
        with DatabasePool().get_session() as s:
            rows = s.execute(text(f"""
                SELECT r.run_id, r.mode, r.strategy, r.strategy_slug, r.status,
                       bs.total_return, bs.total_trades, bs.win_rate, bs.sharpe_ratio
                FROM assethero.runs r
                LEFT JOIN assethero.backtest_summaries bs
                       ON bs.run_id = r.run_id AND bs.is_best = TRUE
                WHERE {where}
                ORDER BY r.created_at DESC
                LIMIT :lim
            """), bind).fetchall()
        return [dict(r._mapping) for r in rows], None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


def _kpi_row(boxes):
    return Div(*[Div(Div(v, cls="v"), Div(l, cls="l")) for l, v in boxes], cls="kpi")


def _runs_table(runs):
    if not runs:
        return P("No crypto runs yet. Run a backtest to populate this.", cls="muted")
    rows = []
    for r in runs:
        ret = r.get("total_return")
        ret_txt = f"{float(ret):.2f}%" if ret is not None else "—"
        cls = "pos" if (ret or 0) >= 0 else "neg"
        rows.append(Tr(
            Td(NotStr(f"<code>{str(r.get('run_id', ''))[:12]}</code>")),
            Td(r.get("mode", "")),
            Td(r.get("strategy") or r.get("strategy_slug") or ""),
            Td(r.get("status", "")),
            Td(ret_txt, cls=f"right {cls}"),
            Td(str(r.get("total_trades") or ""), cls="right"),
        ))
    return Table(
        Thead(Tr(Th("Run"), Th("Mode"), Th("Strategy"), Th("Status"),
                 Th("Return", cls="right"), Th("Trades", cls="right"))),
        Tbody(*rows),
    )


def _agent_options(selected=None):
    from .config import AGENT_CONFIGS, BACKTEST_AGENTS
    opts = []
    for key in BACKTEST_AGENTS:
        label = AGENT_CONFIGS[key]["label"]
        opts.append(Option(label, value=key, selected=(key == selected)))
    return opts


def _exchange_options(selected="kraken"):
    from .config import EXCHANGES
    return [Option(x.capitalize(), value=x, selected=(x == selected)) for x in EXCHANGES]


# --- views ------------------------------------------------------------------

def _dashboard(user):
    from .config import BACKTEST_AGENTS, EXCHANGES
    runs, err = _recent_runs(user_id=user.get("user_id") if user else None)
    center = [H2("Crypto — Dashboard"),
              P("Multi-exchange crypto backtesting & paper trading with an RL "
                "hyperparameter tuner. 8 strategies; order-book & arbitrage are "
                "live-only (paper/backtest excluded).", cls="muted")]
    center.append(Div(_kpi_row([
        ("Strategies", str(len(BACKTEST_AGENTS))),
        ("Exchanges", str(len(EXCHANGES))),
        ("Mode", "Backtest + Paper"),
    ]), cls="card"))
    if err:
        center.append(Div(f"Runs unavailable: {err}", cls="notice err"))
    else:
        center.append(Div(H3("Recent runs"), _runs_table(runs), cls="card"))
    return page("crypto", NAV, *center, user=user, active_nav="/crypto",
                title="AssetHero · Crypto", rail_chips=RAIL_CHIPS)


def _backtest_form(user, result_block=None):
    form = Form(
        Div(
            Div(Label("Strategy"), Select(*_agent_options("momentum"), name="agent"), cls="formrow"),
            Div(Label("Exchange"), Select(*_exchange_options("kraken"), name="exchange"), cls="formrow"),
            style="display:flex;gap:1rem;flex-wrap:wrap",
        ),
        Div(
            Div(Label("Symbol"), Input(name="symbol", value="BTC/USDC"), cls="formrow"),
            Div(Label("Timeframe"), Select(
                Option("1m", value="1m"), Option("5m", value="5m"),
                Option("15m", value="15m"), Option("1h", value="1h", selected=True),
                Option("4h", value="4h"), Option("1d", value="1d"),
                name="timeframe"), cls="formrow"),
            Div(Label("Candles"), Input(name="limit", value="1000", type="number"), cls="formrow"),
            style="display:flex;gap:1rem;flex-wrap:wrap",
        ),
        Div(Label("Initial capital ($)"),
            Input(name="capital", value="10000", type="number", step="100"), cls="formrow"),
        Button("Run backtest", cls="btn", type="submit"),
        method="post", action="/crypto/backtest",
    )
    center = [H2("Crypto — Backtest"),
              P("Fetches historical OHLCV from the exchange (public data; your "
                "keys are used when configured) and runs the strategy with the RL "
                "tuner.", cls="muted"),
              Div(form, cls="card")]
    if result_block is not None:
        center.append(result_block)
    return page("crypto", NAV, *center, user=user, active_nav="/crypto/backtest",
                title="AssetHero · Crypto Backtest", rail_chips=RAIL_CHIPS)


def _result_block(res):
    def pct(x):
        return f"{x * 100:.2f}%"
    boxes = [
        ("Total return", pct(res.total_return)),
        ("Total P&L", f"${res.total_pnl:,.2f}"),
        ("Trades", str(res.total_trades)),
        ("Win rate", pct(res.win_rate)),
        ("Sharpe", f"{res.sharpe:.2f}"),
        ("Max drawdown", pct(res.max_drawdown)),
    ]
    kids = [H3(f"Result — {res.agent_type} on {res.exchange} ({res.symbol} {res.timeframe})"),
            _kpi_row(boxes)]
    if res.run_id:
        kids.append(P(NotStr(f"Saved as run <code>{res.run_id}</code>."),
                      cls="muted", style="margin-top:.8rem"))
    if res.error:
        kids.append(Div(res.error, cls="notice err"))
    return Div(*kids, cls="card")


def register(app, rt, current_user):
    """Attach crypto routes to the FastHTML app. `current_user(session)->dict|None`."""

    def guard(session):
        return current_user(session)

    @rt("/crypto")
    def crypto_home(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return _dashboard(user)

    @rt("/crypto/backtest", methods=["GET"])
    def crypto_backtest_get(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return _backtest_form(user)

    @app.post("/crypto/backtest")
    async def crypto_backtest_post(session, request):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        try:
            from .backtest import run_backtest
            res = run_backtest(
                agent_type=form.get("agent", "momentum"),
                exchange=form.get("exchange", "kraken"),
                symbol=(form.get("symbol") or "BTC/USDC").strip().upper(),
                timeframe=form.get("timeframe", "1h"),
                limit=int(form.get("limit", 1000)),
                initial_balance=float(form.get("capital", 10000)),
                user_id=user.get("user_id"),
            )
            return _backtest_form(user, _result_block(res))
        except Exception as e:  # noqa: BLE001
            return _backtest_form(user, Div(f"Backtest failed: {e}", cls="notice err"))

    @rt("/crypto/runs")
    def crypto_runs(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        runs, err = _recent_runs(limit=30, user_id=user.get("user_id"))
        center = [H2("Crypto — Runs")]
        center.append(Div(f"Runs unavailable: {err}", cls="notice err") if err
                      else Div(_runs_table(runs), cls="card"))
        return page("crypto", NAV, *center, user=user, active_nav="/crypto/runs",
                    title="AssetHero · Crypto Runs", rail_chips=RAIL_CHIPS)

    @app.post("/crypto/assistant")
    async def crypto_assistant(session, request):
        user = guard(session)
        if not user:
            return "Please log in."
        form = await request.form()
        q = (form.get("q") or "").strip().lower()
        return _assistant_answer(q, user)


def _assistant_answer(q: str, user) -> str:
    """Keyless quick-answer assistant for the crypto rail."""
    if q in ("help", "", "?"):
        return ("<b>Try:</b> <code>runs</code>, <code>strategies</code>, "
                "<code>exchanges</code>. Use the Backtest page to run a strategy, "
                "or <code>agent:backtest agent:momentum exchange:kraken</code>.")
    try:
        if q.startswith("strateg"):
            from .config import AGENT_CONFIGS, BACKTEST_AGENTS
            lines = [f"<code>{k}</code> — {AGENT_CONFIGS[k]['label']}" for k in BACKTEST_AGENTS]
            live = [f"<code>{k}</code> — {AGENT_CONFIGS[k]['label']} (live-only)"
                    for k, v in AGENT_CONFIGS.items() if v["live_only"]]
            return "<b>Backtest/paper strategies</b><br>" + "<br>".join(lines) + \
                   "<br><b>Live-only</b><br>" + "<br>".join(live)
        if q.startswith("exchange"):
            from .config import EXCHANGES
            return "<b>Supported exchanges</b><br>" + ", ".join(
                f"<code>{x}</code>" for x in EXCHANGES)
        if q.startswith("run"):
            rows, err = _recent_runs(limit=8, user_id=user.get("user_id") if user else None)
            if err:
                return f"Runs unavailable: {err}"
            if not rows:
                return "No crypto runs yet."
            return "<b>Recent crypto runs</b><br>" + "<br>".join(
                f"<code>{str(r.get('run_id', ''))[:12]}</code> {r.get('strategy', '')} "
                f"— {r.get('status', '')}" for r in rows)
    except Exception as e:  # noqa: BLE001
        return f"assistant error: {e}"
    return (f"I can answer <code>runs</code>, <code>strategies</code>, "
            f"<code>exchanges</code>, or <code>help</code>. (You asked: {q!r})")
