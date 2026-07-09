"""Prediction vertical routes — mounted under /prediction/* by app.py.

Prediction markets (Polymarket) with a weather-edge strategy. Scope is BACKTEST +
PAPER only — there is no real order placement anywhere in this vertical. Rendered in
the shared house-style chat shell (`engine.web.layout.page`).

All heavy machinery (broker HTTP, weather feeds, py_clob_client, DB) is imported
lazily inside handlers, so `import verticals.prediction.routes` succeeds with none of
those packages/services present; handlers catch failures and render a friendly error.
"""
from __future__ import annotations

from html import escape

from fasthtml.common import (
    A, Button, Div, Form, H2, H3, Input, Label, Option, P, Select, Span, Table,
    Tbody, Td, Th, Thead, Tr, NotStr,
)
from starlette.responses import RedirectResponse

from engine.web.layout import page

NAV = [
    ("Dashboard", "/prediction"),
    ("Backtest", "/prediction/backtest"),
    ("Runs", "/prediction/runs"),
]
RAIL_CHIPS = ["runs", "trades", "portfolio", "help"]

# Agent-shortcut groups surfaced under the chat box (command, description).
SHORTCUTS = [
    ("Backtest", [
        ("agent:backtest venue:polymarket city:NYC lookback:7d",
         "Resolution-aware weather-edge backtest"),
        ("agent:backtest venue:polymarket city:London lookback:14d mode:v2",
         "Cross-sectional YES/NO backtest"),
    ]),
    ("Markets", [
        ("markets:weather London", "Search Polymarket weather markets for a city"),
        ("markets:weather NYC", "Scan NYC highest-temperature markets"),
    ]),
    ("Paper Trade", [
        ("paper:buy 100 <market_id>", "Open a $100 paper position on a market"),
        ("paper:sell <order_id>", "Close an open paper position"),
        ("paper:portfolio", "View paper portfolio & PnL"),
    ]),
    ("Reports", [
        ("trades:prediction", "List prediction trades"),
        ("pnl:prediction", "Prediction paper PnL summary"),
        ("runs:prediction", "Recent prediction runs"),
    ]),
]


# --- helpers ----------------------------------------------------------------

def _kpi_row(boxes):
    return Div(*[Div(Div(v, cls="v"), Div(l, cls="l")) for l, v in boxes], cls="kpi")


def _portfolio_card(user):
    """On-chain USDC + positions when a Polymarket wallet is configured."""
    try:
        from engine.brokers.polymarket_broker import PolymarketBroker
        data = PolymarketBroker(user_id=user.get("user_id") if user else None).get_portfolio()
    except Exception as e:  # noqa: BLE001
        return Div(f"Polymarket unavailable: {e}", cls="notice err")
    if "error" in data:
        return Div(
            H3("On-chain wallet"),
            P(data["error"], cls="muted"),
            P(NotStr('Configure it on the <a href="/admin/integrations">Integrations</a> '
                     'page (provider Polymarket).'), cls="muted"),
            cls="card",
        )
    positions = data.get("positions", [])
    boxes = [("USDC balance", f"${float(data.get('balance', 0)):,.2f}"),
             ("Open positions", str(len(positions)))]
    inner = [H3("On-chain wallet"), _kpi_row(boxes)]
    if positions:
        rows = []
        for p in positions:
            pnl = float(p.get("pnl", 0) or 0)
            rows.append(Tr(
                Td((p.get("market") or "")[:40]),
                Td(p.get("outcome", ""), cls="right"),
                Td(f"{float(p.get('size', 0)):,.1f}", cls="right"),
                Td(f"${float(p.get('current_value', 0)):,.2f}", cls="right"),
                Td(f"${pnl:,.2f}", cls=f"right {'pos' if pnl >= 0 else 'neg'}"),
            ))
        inner.append(Table(
            Thead(Tr(Th("Market"), Th("Outcome", cls="right"), Th("Size", cls="right"),
                     Th("Value", cls="right"), Th("PnL", cls="right"))),
            Tbody(*rows)))
    return Div(*inner, cls="card")


def _paper_card(user):
    try:
        from verticals.prediction.paper import portfolio_summary
        s = portfolio_summary(user_id=user.get("user_id") if user else None)
    except Exception as e:  # noqa: BLE001
        return Div(f"Paper portfolio unavailable: {e}", cls="notice err")
    boxes = [
        ("Trades", str(s["total_trades"])),
        ("Open", str(s["open_trades"])),
        ("Realized PnL", f"${s['realized_pnl']:,.2f}"),
        ("ROI", f"{s['roi_pct']:.1f}%"),
    ]
    return Div(H3("Paper portfolio"), _kpi_row(boxes), cls="card")


def _runs_table(runs):
    if not runs:
        return P("No runs yet. Run a backtest to populate this.", cls="muted")
    rows = []
    for r in runs:
        res = r.get("results") or {}
        roi = res.get("final_roi") if isinstance(res, dict) else None
        roi_txt = f"{float(roi):.2f}%" if roi is not None else "—"
        cls = "pos" if (roi or 0) >= 0 else "neg"
        rows.append(Tr(
            Td(NotStr(f"<code>{str(r.get('run_id',''))[:14]}</code>")),
            Td(r.get("mode", "")),
            Td(r.get("strategy") or ""),
            Td(r.get("status", "")),
            Td(roi_txt, cls=f"right {cls}"),
        ))
    return Table(
        Thead(Tr(Th("Run"), Th("Mode"), Th("Strategy"), Th("Status"),
                 Th("ROI", cls="right"))),
        Tbody(*rows))


def _recent_runs(limit, user):
    try:
        from verticals.prediction.paper import recent_runs
        return recent_runs(limit=limit, user_id=user.get("user_id") if user else None), None
    except Exception as e:  # noqa: BLE001
        return [], str(e)


# --- views ------------------------------------------------------------------

def _dashboard(user):
    runs, runs_err = _recent_runs(12, user)
    center = [H2("Prediction — Dashboard"),
              _portfolio_card(user), _paper_card(user)]
    if runs_err:
        center.append(Div(f"Runs unavailable: {runs_err}", cls="notice err"))
    else:
        center.append(Div(H3("Recent runs"), _runs_table(runs), cls="card"))
    return page("prediction", NAV, *center, user=user, active_nav="/prediction",
                title="AssetHero · Prediction", rail_chips=RAIL_CHIPS)


def _backtest_form(user, result_block=None):
    form = Form(
        Div(Label("City"), Input(name="city", value="NYC"), cls="formrow"),
        Div(
            Div(Label("Lookback (days)"), Input(name="lookback_days", value="7", type="number"), cls="formrow"),
            Div(Label("Mode"),
                Select(Option("v1 — best YES", value="v1"),
                       Option("v2 — YES + NO hedge", value="v2"), name="mode"),
                cls="formrow"),
            style="display:flex;gap:1rem;flex-wrap:wrap",
        ),
        Button("Run backtest", cls="btn", type="submit"),
        method="post", action="/prediction/backtest",
    )
    center = [H2("Prediction — Backtest"),
              P("Resolution-aware weather-edge backtest over Polymarket "
                "highest-temperature markets (Visual Crossing settlement, $100/trade).",
                cls="muted"),
              Div(form, cls="card")]
    if result_block is not None:
        center.append(result_block)
    return page("prediction", NAV, *center, user=user, active_nav="/prediction/backtest",
                title="AssetHero · Prediction Backtest", rail_chips=RAIL_CHIPS)


def _result_block(res):
    boxes = [
        ("Final ROI", f"{res.get('final_roi', 0):.2f}%"),
        ("Final PnL", f"${res.get('final_pnl', 0):,.2f}"),
        ("Invested", f"${res.get('total_invested', 0):,.0f}"),
        ("Trades", str(len(res.get("trades", [])))),
        ("Markets found", str(res.get("markets_found", 0))),
    ]
    rows = []
    for t in res.get("trades", [])[:40]:
        pnl = float(t.get("pnl", 0) or 0)
        rows.append(Tr(
            Td(t.get("date", "")),
            Td((t.get("bucket") or "")[:26]),
            Td(t.get("Side", "")),
            Td(f"${t.get('price', 0):.3f}", cls="right"),
            Td(t.get("result", ""), cls="right"),
            Td(f"${pnl:,.2f}", cls=f"right {'pos' if pnl >= 0 else 'neg'}"),
        ))
    table = (Table(Thead(Tr(Th("Date"), Th("Bucket"), Th("Side"), Th("Entry", cls="right"),
                            Th("Result", cls="right"), Th("PnL", cls="right"))),
                   Tbody(*rows)) if rows else P("No qualifying trades in this window.", cls="muted"))
    return Div(H3(f"Result — {res.get('city', '')} ({res.get('period', '')})"),
               _kpi_row(boxes), table, cls="card")


# --- assistant --------------------------------------------------------------

def _parse_kv(q: str) -> dict:
    out = {}
    for tok in q.split():
        if ":" in tok:
            k, v = tok.split(":", 1)
            out[k.lower()] = v
    return out


def _lookback_days(s: str, default: int = 7) -> int:
    s = (s or "").strip().lower().rstrip("d")
    try:
        return int(s)
    except ValueError:
        return default


def _assistant_answer(q: str, user) -> str:
    ql = q.strip()
    low = ql.lower()
    uid = user.get("user_id") if user else None

    if low in ("", "help", "?"):
        return ("<b>Prediction commands</b><br>"
                "<code>markets:weather London</code> — search weather markets<br>"
                "<code>agent:backtest venue:polymarket city:NYC lookback:7d</code> — backtest<br>"
                "<code>paper:portfolio</code> · <code>trades:prediction</code> · "
                "<code>pnl:prediction</code> · <code>runs:prediction</code>")

    try:
        if low.startswith("markets:weather") or low.startswith("markets weather"):
            city = ql.split(None, 1)[1].strip() if len(ql.split(None, 1)) > 1 else ""
            city = city.replace("weather", "", 1).strip() if low.startswith("markets weather") else city
            from engine.brokers.polymarket_broker import PolymarketBroker
            br = PolymarketBroker(user_id=uid)
            markets = br.search_weather_markets(cities=[city] if city else None)[:10]
            if not markets:
                return f"No weather markets found{(' for ' + escape(city)) if city else ''}."
            out = [f"<b>Weather markets{(' — ' + escape(city)) if city else ''}</b>"]
            for m in markets:
                out.append(f"<code>{escape(m.id)}</code> {escape(m.question[:70])} — "
                           f"YES ${m.yes_price:.2f} (liq ${m.liquidity:.0f})")
            return "<br>".join(out)

        if low.startswith("agent:backtest") or low.startswith("agent backtest"):
            kv = _parse_kv(ql)
            city = kv.get("city", "NYC")
            days = _lookback_days(kv.get("lookback", "7d"))
            v2 = kv.get("mode", "").lower() in ("v2", "cross", "hedge")
            from engine.brokers.polymarket_broker import PolymarketBroker
            from engine.feeds.visualcrossing_feed import VisualCrossingFeed
            from verticals.prediction.backtest import run_backtest
            from verticals.prediction.paper import record_backtest_run
            res = run_backtest(PolymarketBroker(user_id=uid), VisualCrossingFeed(user_id=uid),
                               city=city, lookback_days=days, v2_mode=v2)
            try:
                record_backtest_run(uid, city, res, config={"lookback_days": days, "v2": v2})
            except Exception:  # noqa: BLE001
                pass
            return (f"<b>Backtest — {escape(city)}</b> ({escape(str(res.get('period','')))})<br>"
                    f"ROI {res.get('final_roi',0):.2f}% · PnL ${res.get('final_pnl',0):,.2f} · "
                    f"{len(res.get('trades',[]))} trades · {res.get('markets_found',0)} markets")

        if low.startswith("paper:buy") or low.startswith("paper buy"):
            parts = ql.split()
            if len(parts) < 3:
                return "Usage: <code>paper:buy &lt;amount&gt; &lt;market_id&gt;</code>"
            amount = float(parts[1])
            market_id = parts[2]
            from engine.brokers.polymarket_broker import PolymarketBroker
            from verticals.prediction.paper import record_paper_trade
            m = PolymarketBroker(user_id=uid).get_market_by_id(market_id)
            if not m or m.yes_price <= 0:
                return f"Could not price market <code>{escape(market_id)}</code>."
            t = record_paper_trade(uid, market_id, m.question, "YES", amount, m.yes_price)
            return (f"Paper buy recorded: {t['shares']:.1f} YES shares @ ${m.yes_price:.3f} "
                    f"(${amount:.0f}) — order <code>{escape(t['order_id'])}</code>")

        if low.startswith("paper:sell") or low.startswith("paper sell"):
            parts = ql.split()
            if len(parts) < 2:
                return "Usage: <code>paper:sell &lt;order_id&gt;</code>"
            from engine.brokers.polymarket_broker import PolymarketBroker  # for price
            from verticals.prediction.paper import fetch_paper_trades, close_paper_trade
            open_t = [t for t in fetch_paper_trades(user_id=uid) if t.get("exit_time") is None]
            match = next((t for t in open_t if str(t.get("order_id", "")).endswith(parts[1])), None)
            if not match:
                return f"No open paper position matching <code>{escape(parts[1])}</code>."
            m = PolymarketBroker(user_id=uid).get_market_by_id(str(match["symbol"]))
            exit_price = m.yes_price if m else float(match["entry_price"])
            r = close_paper_trade(uid, match["order_id"], exit_price)
            return f"Closed <code>{escape(str(match['order_id']))}</code> @ ${exit_price:.3f} — PnL ${r['pnl']:,.2f}"

        if low.startswith("paper:portfolio") or low.startswith("paper portfolio"):
            from verticals.prediction.paper import portfolio_summary
            s = portfolio_summary(user_id=uid)
            return (f"<b>Paper portfolio</b><br>Trades {s['total_trades']} "
                    f"(open {s['open_trades']}, closed {s['closed_trades']})<br>"
                    f"Invested ${s['total_invested']:,.2f} · Realized PnL "
                    f"${s['realized_pnl']:,.2f} · Win rate {s['win_rate']:.1f}% · "
                    f"ROI {s['roi_pct']:.1f}%")

        if low.startswith("trades:prediction") or low.startswith("trades prediction"):
            from verticals.prediction.paper import fetch_paper_trades
            rows = fetch_paper_trades(user_id=uid, limit=12)
            if not rows:
                return "No prediction trades yet."
            out = ["<b>Prediction trades</b>"]
            for t in rows:
                pnl = t.get("pnl")
                pnl_txt = f"${float(pnl):,.2f}" if pnl is not None else "open"
                out.append(f"<code>{escape(str(t.get('order_id','')))}</code> "
                           f"{escape(str(t.get('direction','')))} "
                           f"{float(t.get('shares') or 0):.1f}@${float(t.get('entry_price') or 0):.3f} — {pnl_txt}")
            return "<br>".join(out)

        if low.startswith("pnl:prediction") or low.startswith("pnl prediction"):
            from verticals.prediction.paper import portfolio_summary
            s = portfolio_summary(user_id=uid)
            return (f"<b>Prediction PnL</b><br>Realized ${s['realized_pnl']:,.2f} · "
                    f"ROI {s['roi_pct']:.1f}% · Win rate {s['win_rate']:.1f}% "
                    f"({s['closed_trades']} closed)")

        if low.startswith("runs:prediction") or low.startswith("runs prediction") or low.startswith("run"):
            from verticals.prediction.paper import recent_runs
            rows = recent_runs(limit=8, user_id=uid)
            if not rows:
                return "No runs yet."
            out = ["<b>Recent runs</b>"]
            for r in rows:
                out.append(f"<code>{escape(str(r.get('run_id',''))[:14])}</code> "
                           f"{escape(str(r.get('mode','')))} — {escape(str(r.get('status','')))}")
            return "<br>".join(out)

    except Exception as e:  # noqa: BLE001
        return f"<span class='neg'>error: {escape(str(e))}</span>"

    return (f"I can answer <code>markets:weather</code>, <code>agent:backtest</code>, "
            f"<code>paper:portfolio</code>, <code>trades:prediction</code>, "
            f"<code>runs:prediction</code>, or <code>help</code>. (You asked: {escape(q)})")


# --- registration -----------------------------------------------------------

def register(app, rt, current_user):
    """Attach prediction routes. `current_user(session)->dict|None`."""

    def guard(session):
        return current_user(session)

    @rt("/prediction")
    def prediction_home(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return _dashboard(user)

    @rt("/prediction/backtest", methods=["GET"])
    def prediction_backtest_get(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return _backtest_form(user)

    @app.post("/prediction/backtest")
    async def prediction_backtest_post(session, request):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        form = await request.form()
        try:
            from engine.brokers.polymarket_broker import PolymarketBroker
            from engine.feeds.visualcrossing_feed import VisualCrossingFeed
            from verticals.prediction.backtest import run_backtest
            from verticals.prediction.paper import record_backtest_run
            uid = user.get("user_id")
            city = (form.get("city") or "NYC").strip()
            days = int(form.get("lookback_days", 7) or 7)
            v2 = (form.get("mode", "v1") == "v2")
            res = run_backtest(PolymarketBroker(user_id=uid), VisualCrossingFeed(user_id=uid),
                               city=city, lookback_days=days, v2_mode=v2)
            try:
                record_backtest_run(uid, city, res, config={"lookback_days": days, "v2": v2})
            except Exception:  # noqa: BLE001
                pass
            return _backtest_form(user, _result_block(res))
        except Exception as e:  # noqa: BLE001
            return _backtest_form(user, Div(f"Backtest failed: {e}", cls="notice err"))

    @rt("/prediction/runs")
    def prediction_runs(session):
        user = guard(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        runs, err = _recent_runs(30, user)
        center = [H2("Prediction — Runs")]
        center.append(Div(f"Runs unavailable: {err}", cls="notice err") if err
                      else Div(_runs_table(runs), cls="card"))
        return page("prediction", NAV, *center, user=user, active_nav="/prediction/runs",
                    title="AssetHero · Prediction Runs", rail_chips=RAIL_CHIPS)

    @app.post("/prediction/assistant")
    async def prediction_assistant(session, request):
        user = guard(session)
        if not user:
            return "Please log in."
        form = await request.form()
        return _assistant_answer((form.get("q") or "").strip(), user)
