"""FX / Macro vertical routes — mounted under /fx/* by app.py.

Surfaces:
  /fx            dashboard: market movers + currency-pair snapshots + an FX chart
  /fx/backtest   GET form + POST run of the momentum backtest on one pair
  /fx/news       macro-news history + trending categories + a manual Refresh action
  POST /fx/assistant   desk research assistant (returns HTML for the chat bubble)

Scope is BACKTEST + macro-news RESEARCH only — there is no FX broker, so paper
trading is simulated via the backtester. All heavy deps are imported lazily
inside the vertical modules, so importing this module is always safe.
"""
from __future__ import annotations

from fasthtml.common import (
    A, Button, Div, Form, H2, H3, Input, Label, Option, P, Select, Span, Table,
    Tbody, Td, Th, Thead, Tr, NotStr,
)
from starlette.responses import RedirectResponse

from engine.web.layout import page
from engine.integrations import resolve
from .config import SUPPORTED_PAIRS, SUPPORTED_PERIODS, CURRENCY_PAIRS, EVENT_CATEGORIES

NAV = [
    ("Dashboard", "/fx"),
    ("Backtest", "/fx/backtest"),
    ("News", "/fx/news"),
]
RAIL_CHIPS = ["movers", "news", "backtest", "help"]

# Discoverable command groups for this vertical (chat shortcuts).
SHORTCUTS = [
    ("Research", [
        ("movers", "Top macro market movers (last 48h)"),
        ("news central-bank", "Central-bank macro news history"),
        ("fx EURUSD", "Live spot snapshot for a currency pair"),
    ]),
    ("Charts", [
        ("chart fx EURUSD", "FX rate line chart"),
        ("chart treasury", "US 10Y Treasury yield chart"),
    ]),
    ("Backtest", [
        ("backtest EURUSD lookback:30 tp:2 sl:1", "Run a momentum backtest on a pair"),
        ("compare EURUSD", "Compare conservative/balanced/aggressive configs"),
        ("suggest trending EURUSD", "Suggest params for a macro scenario"),
    ]),
]


# --- shared render helpers --------------------------------------------------

def _kpi_row(boxes):
    return Div(*[Div(Div(v, cls="v"), Div(l, cls="l")) for l, v in boxes], cls="kpi")


def _movers_table(rows):
    if not rows:
        return P("No enriched movers yet. Refresh news (with an xAI key) to populate.", cls="muted")
    trs = []
    for a in rows:
        d = (a.get("predicted_direction") or "").upper()
        mag = a.get("predicted_magnitude") or 0
        cls = "pos" if (mag or 0) >= 0 else "neg"
        trs.append(Tr(
            Td(a.get("currency_tag") or ""),
            Td(d, cls=cls),
            Td(f"{mag:+.2f}%", cls=f"right {cls}"),
            Td(A(a["title"][:70], href=a["url"], target="_blank")),
            Td(a.get("source_name") or "", cls="muted"),
        ))
    return Table(Thead(Tr(Th("Ccy"), Th("Dir"), Th("Impact", cls="right"),
                          Th("Headline"), Th("Source"))), Tbody(*trs))


def _news_table(rows):
    if not rows:
        return P("No macro news stored yet. Use the Refresh button above.", cls="muted")
    trs = []
    for a in rows:
        pub = a.get("published_at")
        pub_txt = pub.strftime("%Y-%m-%d") if hasattr(pub, "strftime") else ""
        trs.append(Tr(
            Td(pub_txt, cls="muted"),
            Td(a.get("currency_tag") or ""),
            Td(a.get("event_category") or ""),
            Td(A(a["title"][:80], href=a["url"], target="_blank")),
            Td(a.get("source_name") or "", cls="muted"),
        ))
    return Table(Thead(Tr(Th("Date"), Th("Ccy"), Th("Category"), Th("Headline"), Th("Source"))),
                 Tbody(*trs))


def _pair_cards(snaps):
    boxes = []
    for s in snaps:
        if s.get("error"):
            continue
        c = "pos" if s["change"] >= 0 else "neg"
        boxes.append(Div(
            Div(f"{s['current']:.5f}", cls="v"),
            Div(f"{s['pair']}  ", Span(f"{s['change_pct']:+.2f}%", cls=c), cls="l"),
        ))
    return Div(*boxes, cls="kpi") if boxes else P("FX quotes unavailable.", cls="muted")


# --- views ------------------------------------------------------------------

def _dashboard(user):
    from . import news as news_mod
    from . import market_data as md
    uid = user.get("user_id") if user else None
    center = [H2("FX / Macro — Dashboard"),
              P("Momentum backtesting + macro-news research. Paper trading is simulated "
                "(backtest only) — there is no FX broker.", cls="muted")]

    # currency pair snapshots (yfinance; degrade gracefully)
    try:
        snaps = [md.analyze_pair(p["pair"], period="5d") for p in CURRENCY_PAIRS]
        center.append(Div(H3("Currency pairs"), _pair_cards(snaps), cls="card"))
    except Exception as e:  # noqa: BLE001
        center.append(Div(f"FX quotes unavailable: {e}", cls="notice err"))

    # a default FX chart (server-rendered so the Plotly script runs)
    try:
        data = md.get_fx_history("EURUSD", period="1y")
        if data["dates"]:
            chart = md.build_line_chart_html("EURUSD (1y)", data["dates"], data["rates"],
                                             "EURUSD", y_label="Rate", div_id="fx-dash-chart")
            center.append(Div(H3("EUR/USD — 1Y"), NotStr(chart), cls="card"))
    except Exception:  # noqa: BLE001
        pass

    # market movers from macro news
    try:
        movers = news_mod.market_movers(hours=48, user_id=uid)
        center.append(Div(H3("Macro market movers"), _movers_table(movers), cls="card"))
    except Exception as e:  # noqa: BLE001
        center.append(Div(f"News unavailable: {e}", cls="notice err"))

    return page("fx", NAV, *center, user=user, active_nav="/fx",
                title="AssetHero · FX / Macro", rail_chips=RAIL_CHIPS)


def _backtest_form(user, result_block=None):
    pair_opts = [Option(p, value=p) for p in SUPPORTED_PAIRS]
    period_opts = [Option(p, value=p, selected=(p == "1y")) for p in SUPPORTED_PERIODS]
    form = Form(
        Div(
            Div(Label("Pair"), Select(*pair_opts, name="pair"), cls="formrow"),
            Div(Label("Period"), Select(*period_opts, name="period"), cls="formrow"),
            style="display:flex;gap:1rem",
        ),
        Div(
            Div(Label("Lookback (days)"), Input(name="lookback", value="20", type="number"), cls="formrow"),
            Div(Label("Momentum %"), Input(name="momentum_threshold", value="0.5", type="number", step="0.1"), cls="formrow"),
            Div(Label("Take-profit %"), Input(name="take_profit", value="1.0", type="number", step="0.1"), cls="formrow"),
            Div(Label("Stop-loss %"), Input(name="stop_loss", value="0.5", type="number", step="0.1"), cls="formrow"),
            Div(Label("Position size %"), Input(name="position_size_pct", value="10", type="number", step="1"), cls="formrow"),
            style="display:flex;gap:1rem;flex-wrap:wrap",
        ),
        Button("Run backtest", cls="btn", type="submit"),
        method="post", action="/fx/backtest",
    )
    center = [H2("FX / Macro — Backtest"),
              P("Simulated momentum backtest on yfinance FX data. Results persist to the shared "
                "assethero backtest tables (vertical=fx).", cls="muted"),
              Div(form, cls="card")]
    if result_block is not None:
        center.append(result_block)
    return page("fx", NAV, *center, user=user, active_nav="/fx/backtest",
                title="AssetHero · FX Backtest", rail_chips=RAIL_CHIPS)


def _result_block(res):
    from . import backtest as bt
    parts = [NotStr(bt.metrics_table_html(res))]
    eq = bt.equity_curve_html(res)
    if eq:
        parts.append(NotStr(eq))
    parts.append(NotStr(bt.trades_table_html(res)))
    return Div(H3("Result"), *parts, cls="card")


def _news_view(user, flash=None):
    from . import news as news_mod
    uid = user.get("user_id") if user else None
    refresh = Form(
        Button("Refresh news", cls="btn", type="submit"),
        Span("  Fetches RSS, classifies, and (with an xAI key) enriches new articles.", cls="muted"),
        method="post", action="/fx/news/refresh", style="display:flex;align-items:center;gap:.6rem",
    )
    center = [H2("FX / Macro — News")]
    if flash:
        center.append(Div(flash, cls="flash"))
    center.append(Div(refresh, cls="card"))
    try:
        trending = news_mod.trending_categories(hours=48, user_id=uid)
        if trending:
            boxes = [(t["name"], str(t["article_count"])) for t in trending]
            center.append(Div(H3("Trending categories (48h)"), _kpi_row(boxes), cls="card"))
    except Exception:  # noqa: BLE001
        pass
    try:
        rows = news_mod.recent_news(limit=40, user_id=uid)
        center.append(Div(H3("Recent macro news"), _news_table(rows), cls="card"))
    except Exception as e:  # noqa: BLE001
        center.append(Div(f"News unavailable: {e}", cls="notice err"))
    return page("fx", NAV, *center, user=user, active_nav="/fx/news",
                title="AssetHero · FX News", rail_chips=RAIL_CHIPS)


# --- registration -----------------------------------------------------------

def register(app, rt, current_user):
    """Attach FX routes. `current_user(session) -> dict|None`."""

    def guard(session):
        return current_user(session)

    @rt("/fx")
    def fx_home(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return _dashboard(user)

    @rt("/fx/backtest", methods=["GET"])
    def fx_backtest_get(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return _backtest_form(user)

    @app.post("/fx/backtest")
    async def fx_backtest_post(session, request):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        try:
            from . import backtest as bt
            res = bt.run_momentum_backtest(
                pair=form.get("pair", "EURUSD"),
                period=form.get("period", "1y"),
                lookback=int(form.get("lookback", 20)),
                momentum_threshold=float(form.get("momentum_threshold", 0.5)),
                take_profit=float(form.get("take_profit", 1.0)),
                stop_loss=float(form.get("stop_loss", 0.5)),
                position_size_pct=float(form.get("position_size_pct", 10)),
                user_id=user.get("user_id"),
            )
            if res.get("error"):
                return _backtest_form(user, Div(res["error"], cls="notice err"))
            return _backtest_form(user, _result_block(res))
        except Exception as e:  # noqa: BLE001
            return _backtest_form(user, Div(f"Backtest failed: {e}", cls="notice err"))

    @rt("/fx/news", methods=["GET"])
    def fx_news_get(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return _news_view(user)

    @app.post("/fx/news/refresh")
    async def fx_news_refresh(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        uid = user.get("user_id")
        try:
            from . import news as news_mod
            xai = resolve(uid, "xai", "api_key")
            summary = news_mod.refresh_news(user_id=uid, xai_key=xai)
            flash = (f"Refreshed: {summary['inserted']} new articles, "
                     f"{summary['enriched']} enriched"
                     + (f" · {len(summary['errors'])} source errors" if summary["errors"] else ""))
        except Exception as e:  # noqa: BLE001
            flash = f"Refresh failed: {e}"
        return _news_view(user, flash=flash)

    @app.post("/fx/assistant")
    async def fx_assistant(session, request):
        user = guard(session)
        if not user:
            return "Please log in."
        form = await request.form()
        q = (form.get("q") or "").strip()
        from . import chat
        return chat.desk_answer(q, user_id=user.get("user_id"))
