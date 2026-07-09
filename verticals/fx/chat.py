"""FX desk research assistant.

Two layers:
  * Deterministic command router (``desk_answer``) — handles the SHORTCUTS
    (movers, news, fx PAIR, chart …, backtest …, compare …, suggest …) with no
    LLM, returning inline HTML for the chat bubble / workspace.
  * Optional LLM desk agent (``llm_answer``) — an xAI Grok tool-calling agent
    (like macrohero's chat_service), used for free-form questions when an xAI
    key is available. langchain is imported lazily.

Note: chat bubbles set innerHTML, which does NOT execute <script> tags, so the
router returns tables/text for chat; interactive Plotly charts render in the
server-rendered workspace panes (dashboard / backtest / news pages).
"""
from __future__ import annotations

import logging

from engine.integrations import resolve
from . import backtest as bt
from . import market_data as md
from . import news as news_mod
from .config import SUPPORTED_PAIRS, CATEGORY_SLUGS

logger = logging.getLogger(__name__)


# --- helpers ----------------------------------------------------------------

def md_to_html(text: str) -> str:
    try:
        import markdown
        return markdown.markdown(text, extensions=["extra", "nl2br", "sane_lists"])
    except Exception:  # noqa: BLE001
        safe = (text or "").replace("\n\n", "</p><p>").replace("\n", "<br>")
        return f"<p>{safe}</p>"


def _parse_params(tokens: list[str]) -> dict:
    """Parse ``key:value`` tokens (lookback/tp/sl/period/momentum/size)."""
    out: dict = {}
    alias = {"tp": "take_profit", "sl": "stop_loss", "mom": "momentum_threshold",
             "size": "position_size_pct", "lb": "lookback"}
    for tok in tokens:
        if ":" not in tok:
            continue
        k, _, v = tok.partition(":")
        k = alias.get(k.lower(), k.lower())
        if k == "period":
            out["period"] = v
        elif k in ("lookback",):
            try:
                out[k] = int(v)
            except ValueError:
                pass
        elif k in ("take_profit", "stop_loss", "momentum_threshold", "position_size_pct"):
            try:
                out[k] = float(v)
            except ValueError:
                pass
    return out


def _movers_html(user_id):
    rows = news_mod.market_movers(hours=48, user_id=user_id)
    if not rows:
        return ("<p class='muted'>No enriched market movers yet. Use the "
                "<b>Refresh</b> action on the News page (needs an xAI key for enrichment).</p>")
    out = "<p style='font-weight:700;margin:.2rem 0'>Top macro market movers (48h)</p><ul>"
    for a in rows:
        d = (a.get("predicted_direction") or "").upper()
        mag = a.get("predicted_magnitude") or 0
        cur = a.get("currency_tag") or ""
        src = a.get("source_name") or ""
        out += (f"<li><b>{d} {mag:+.2f}% {cur}</b> "
                f"<a href='{a['url']}' target='_blank'>{a['title']}</a>"
                f"<span class='muted'> — {src}</span></li>")
    return out + "</ul>"


def _news_html(user_id, category=""):
    rows = news_mod.recent_news(limit=15, category=category, user_id=user_id)
    if not rows:
        return "<p class='muted'>No macro news stored yet. Use the <b>Refresh</b> action on the News page.</p>"
    head = f"Recent macro news{f' · {category}' if category else ''}"
    out = f"<p style='font-weight:700;margin:.2rem 0'>{head}</p><ul>"
    for a in rows:
        cur = f" ({a['currency_tag']})" if a.get("currency_tag") else ""
        src = f" — {a['source_name']}" if a.get("source_name") else ""
        out += f"<li><a href='{a['url']}' target='_blank'>{a['title']}</a><span class='muted'>{cur}{src}</span></li>"
    return out + "</ul>"


def _pair_html(pair):
    snap = md.analyze_pair(pair, period="5d")
    if snap.get("error"):
        return f"<p class='muted'>{snap['error']}</p>"
    c = "#10B981" if snap["change"] >= 0 else "#EF4444"
    return (f"<p style='font-weight:700'>{snap['pair']} <span class='muted'>({snap['period']})</span></p>"
            f"<table>"
            f"<tr><td>Current</td><td class='right'>{snap['current']:.5f}</td></tr>"
            f"<tr><td>Open</td><td class='right'>{snap['open']:.5f}</td></tr>"
            f"<tr><td>Change</td><td class='right' style='color:{c}'>{snap['change']:+.5f} ({snap['change_pct']:+.2f}%)</td></tr>"
            f"<tr><td>High</td><td class='right'>{snap['high']:.5f}</td></tr>"
            f"<tr><td>Low</td><td class='right'>{snap['low']:.5f}</td></tr>"
            f"</table>")


def _backtest_html(user_id, pair, params):
    res = bt.run_momentum_backtest(pair=pair, user_id=user_id, **params)
    if res.get("error"):
        return f"<p class='muted'>{res['error']}</p>"
    return bt.metrics_table_html(res) + bt.trades_table_html(res)


# --- deterministic command router ------------------------------------------

def desk_answer(query: str, user_id: str | None = None) -> str:
    """Return inline HTML for a desk command or free-form question."""
    q = (query or "").strip()
    if not q:
        return _help_html()
    toks = q.split()
    cmd = toks[0].lower()

    try:
        if cmd in ("help", "?"):
            return _help_html()
        if cmd == "movers":
            return _movers_html(user_id)
        if cmd == "news":
            cat = toks[1].lower() if len(toks) > 1 and toks[1].lower() in CATEGORY_SLUGS else ""
            return _news_html(user_id, cat)
        if cmd == "fx" and len(toks) > 1:
            return _pair_html(toks[1])
        if cmd == "chart":
            return _chart_html(toks[1:])
        if cmd == "backtest" and len(toks) > 1:
            return _backtest_html(user_id, toks[1], _parse_params(toks[2:]))
        if cmd == "compare" and len(toks) > 1:
            return bt.compare_table_html(bt.compare_strategies(toks[1], user_id=user_id))
        if cmd == "suggest":
            # suggest <scenario words...> <PAIR>
            pair = next((t for t in toks[1:] if t.upper().replace("/", "") in SUPPORTED_PAIRS), "EURUSD")
            scenario = " ".join(t for t in toks[1:] if t.upper().replace("/", "") not in SUPPORTED_PAIRS)
            sug = bt.suggest_parameters(scenario or "default", pair)
            p = sug["recommended_parameters"]
            return (f"<p style='font-weight:700'>Suggested params · {sug['pair']} · {sug['regime']}</p>"
                    f"<p class='muted'>{sug['scenario']}</p>"
                    f"<p>lookback <b>{p['lookback']}d</b>, TP <b>{p['take_profit']}%</b>, "
                    f"SL <b>{p['stop_loss']}%</b>, momentum <b>{p['momentum_threshold']}%</b></p>"
                    f"<p class='muted'>Run: <code>backtest {sug['pair']} lookback:{p['lookback']} "
                    f"tp:{p['take_profit']} sl:{p['stop_loss']}</code></p>")
    except Exception as e:  # noqa: BLE001
        logger.error(f"fx desk_answer error: {e}")
        return f"<p class='muted'>Desk error: {e}</p>"

    # free-form -> LLM agent if a key is configured
    ans = llm_answer(q, user_id)
    return ans if ans else _help_html(unknown=q)


def _chart_html(args: list[str]) -> str:
    """chart fx PAIR | chart treasury | chart fx-treasury PAIR — server-render note."""
    kind = args[0].lower() if args else "fx"
    if kind in ("fx",) and len(args) > 1:
        data = md.get_fx_history(args[1], period="1y")
        if not data["dates"]:
            return f"<p class='muted'>No FX data for {args[1]}.</p>"
        return md.build_line_chart_html(f"{data['pair']} (1y)", data["dates"], data["rates"],
                                        data["pair"], y_label="Rate", div_id="fx-chat-chart")
    if kind in ("treasury", "ust"):
        return ("<p class='muted'>Treasury chart renders on the "
                "<a href='/fx/news'>News page</a> (needs an EODHD key).</p>")
    return "<p class='muted'>Usage: <code>chart fx EURUSD</code> or <code>chart treasury</code>.</p>"


def _help_html(unknown: str = "", **_) -> str:
    pre = f"<p class='muted'>Not a known command: <code>{unknown}</code></p>" if unknown else ""
    return (pre + "<p><b>FX desk commands</b></p><ul>"
            "<li><code>movers</code> — top macro market movers</li>"
            "<li><code>news [central-bank|inflation|…]</code> — macro news history</li>"
            "<li><code>fx EURUSD</code> — live spot snapshot</li>"
            "<li><code>chart fx EURUSD</code> · <code>chart treasury</code></li>"
            "<li><code>backtest EURUSD lookback:30 tp:2 sl:1</code></li>"
            "<li><code>compare EURUSD</code> · <code>suggest trending EURUSD</code></li>"
            "</ul><p class='muted'>Free-form macro questions use the xAI desk agent when a key is set.</p>")


# --- optional LLM desk agent (xAI Grok, tool-calling) -----------------------

SYSTEM_PROMPT = """You are the AssetHero FX Macro desk analyst. You help users develop FX and
interest-rate trading ideas from macro news, central-bank policy and economic data, and you run
momentum backtests. Use the tools aggressively. Structure answers like a trading desk: a short
macro thesis, concrete trade expressions (bold **Trade:**), and a ranked summary table. End with
2-4 concrete, executable backtest suggestions tied to the trades you named. Use markdown."""


def _lc_tools(user_id):
    """Build langchain StructuredTools bound to this request's user_id."""
    from langchain_core.tools import StructuredTool

    def t_movers() -> str:
        rows = news_mod.market_movers(hours=48, user_id=user_id)
        if not rows:
            return "No market movers stored."
        return "\n".join(f"- {(a.get('predicted_direction') or '').upper()} "
                         f"{(a.get('predicted_magnitude') or 0):+.2f}% {a.get('currency_tag') or ''} "
                         f"{a['title']}" for a in rows)

    def t_news(category: str = "") -> str:
        cat = category if category in CATEGORY_SLUGS else ""
        rows = news_mod.recent_news(limit=12, category=cat, user_id=user_id)
        if not rows:
            return "No macro news stored."
        return "\n".join(f"- {a['title']} ({a.get('currency_tag') or ''})" for a in rows)

    def t_pair(pair: str) -> str:
        s = md.analyze_pair(pair, period="5d")
        if s.get("error"):
            return s["error"]
        return (f"{s['pair']}: current {s['current']:.5f}, change {s['change']:+.5f} "
                f"({s['change_pct']:+.2f}%), high {s['high']:.5f}, low {s['low']:.5f}")

    def t_backtest(pair: str, lookback: int = 20, take_profit: float = 1.0,
                   stop_loss: float = 0.5, period: str = "1y") -> str:
        r = bt.run_momentum_backtest(pair=pair, lookback=lookback, take_profit=take_profit,
                                     stop_loss=stop_loss, period=period, user_id=user_id)
        if r.get("error"):
            return r["error"]
        m = r["metrics"]
        return (f"Backtest {r['pair']} momentum (run {r['run_id'][:8]}): return {m['total_return']:+.2f}%, "
                f"Sharpe {m['sharpe_ratio']:.2f}, maxDD {m['max_drawdown']:.2f}%, "
                f"win {m['win_rate']:.1f}%, {m['total_trades']} trades.")

    def t_suggest(scenario: str, pair: str) -> str:
        import json
        return json.dumps(bt.suggest_parameters(scenario, pair))

    return [
        StructuredTool.from_function(t_movers, name="get_market_movers",
                                     description="Top macro market movers ranked by predicted FX impact."),
        StructuredTool.from_function(t_news, name="get_recent_macro_news",
                                     description="Recent macro news; optional category slug."),
        StructuredTool.from_function(t_pair, name="analyze_currency_pair",
                                     description="Live FX spot snapshot for a pair like EURUSD."),
        StructuredTool.from_function(t_backtest, name="backtest_fx_strategy",
                                     description="Backtest a momentum FX strategy; returns metrics."),
        StructuredTool.from_function(t_suggest, name="suggest_parameters",
                                     description="Suggest backtest params for a macro scenario + pair."),
    ]


def llm_answer(query: str, user_id: str | None = None) -> str | None:
    """Run the xAI desk agent (one tool round-trip). Returns HTML or None if no key."""
    key = resolve(user_id, "xai", "api_key")
    if not key:
        return None
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        from .config import LLM
        tools = _lc_tools(user_id)
        tool_map = {t.name: t for t in tools}
        llm = ChatOpenAI(api_key=key, base_url="https://api.x.ai/v1", model=LLM["model"],
                         temperature=LLM["temperature"], max_tokens=LLM["max_tokens"])
        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=query)]
        ai = llm.bind_tools(tools).invoke(messages)
        messages.append(ai)
        for tc in getattr(ai, "tool_calls", []) or []:
            fn = tool_map.get(tc["name"])
            try:
                result = fn.invoke(tc["args"]) if fn else f"unknown tool {tc['name']}"
            except Exception as e:  # noqa: BLE001
                result = f"tool error: {e}"
            messages.append(ToolMessage(content=str(result), tool_call_id=tc.get("id", tc["name"])))
        final = llm.invoke(messages) if getattr(ai, "tool_calls", None) else ai
        return md_to_html(final.content or "")
    except Exception as e:  # noqa: BLE001
        logger.error(f"fx llm_answer error: {e}")
        return f"<p class='muted'>Desk agent error: {e}</p>"
