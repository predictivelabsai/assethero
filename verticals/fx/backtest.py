"""FX momentum backtest + metrics, persisted to the shared assethero backtest
tables (runs / backtest_summaries / trades) with vertical='fx'.

There is NO FX broker in this platform — this is a SIMULATED backtest only (no
live execution). numpy is imported lazily so importing this module is cheap.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from .config import SUPPORTED_PAIRS, SUPPORTED_PERIODS
from .market_data import get_fx_ohlc, build_equity_curve_html

logger = logging.getLogger(__name__)


# --- DB helpers -------------------------------------------------------------

def _pool():
    from utils.db.db_pool import DatabasePool
    return DatabasePool()


def _exec(sql: str, params: dict | None = None):
    from sqlalchemy import text
    with _pool().get_session() as s:
        s.execute(text(sql), params or {})


def strategy_slug(pair: str, lookback: int, tp: float, sl: float, period: str) -> str:
    return f"fx-mom-{pair.lower()}-{lookback}d-{tp}tp-{sl}sl-{period}"


# --- metrics ----------------------------------------------------------------

def _calculate_metrics(trades: list[dict], initial_capital: float) -> dict:
    import numpy as np
    if not trades:
        return {"total_return": 0, "total_pnl": 0, "win_rate": 0, "sharpe_ratio": 0,
                "max_drawdown": 0, "total_trades": 0, "annualized_return": 0,
                "final_capital": initial_capital}
    total_pnl = sum(t["pnl"] for t in trades)
    final_capital = initial_capital + total_pnl
    total_return = (total_pnl / initial_capital) * 100
    winners = [t for t in trades if t["pnl"] > 0]
    win_rate = (len(winners) / len(trades)) * 100 if trades else 0
    returns = [t["pnl_pct"] / 100 for t in trades]
    sharpe = (np.mean(returns) / np.std(returns) * np.sqrt(252)) if len(returns) > 1 and np.std(returns) > 0 else 0
    equity = [initial_capital]
    for t in trades:
        equity.append(equity[-1] + t["pnl"])
    peak, max_dd = equity[0], 0
    for val in equity:
        peak = max(peak, val)
        dd = (peak - val) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)
    days = len(set(t.get("entry_date", "") for t in trades))
    years = max(days / 252, 0.01)
    ann_return = ((final_capital / initial_capital) ** (1 / years) - 1) * 100
    return {
        "total_return": round(total_return, 2), "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1), "sharpe_ratio": round(float(sharpe), 2),
        "max_drawdown": round(max_dd, 2), "total_trades": len(trades),
        "annualized_return": round(ann_return, 2), "final_capital": round(final_capital, 2),
    }


# --- backtest engine --------------------------------------------------------

def run_momentum_backtest(
    pair: str = "EURUSD", period: str = "1y", initial_capital: float = 100000,
    lookback: int = 20, momentum_threshold: float = 0.5, take_profit: float = 1.0,
    stop_loss: float = 0.5, position_size_pct: float = 10,
    user_id: str | None = None, persist: bool = True,
) -> dict:
    pair = pair.upper().replace("/", "")
    if pair not in SUPPORTED_PAIRS:
        return {"error": f"Unsupported pair {pair}. Supported: {', '.join(SUPPORTED_PAIRS)}"}
    if period not in SUPPORTED_PERIODS:
        return {"error": f"Unsupported period {period}. Supported: {', '.join(SUPPORTED_PERIODS)}"}

    data = get_fx_ohlc(pair, period)
    closes, dates = data.get("closes", []), data.get("dates", [])
    if len(closes) < lookback + 5:
        return {"error": f"Not enough data for {pair} with lookback {lookback}"}
    highs, lows = data["highs"], data["lows"]

    trades: list[dict] = []
    capital = initial_capital
    i = lookback
    while i < len(closes) - 1:
        momentum = ((closes[i] - closes[i - lookback]) / closes[i - lookback]) * 100
        if abs(momentum) >= momentum_threshold:
            direction = "long" if momentum > 0 else "short"
            entry_price = closes[i]
            pos_size = capital * (position_size_pct / 100)
            units = pos_size / entry_price
            tp_price = entry_price * (1 + take_profit / 100) if direction == "long" else entry_price * (1 - take_profit / 100)
            sl_price = entry_price * (1 - stop_loss / 100) if direction == "long" else entry_price * (1 + stop_loss / 100)
            hit_tp = hit_sl = False
            exit_idx = min(i + 10, len(closes) - 1)
            exit_price = closes[exit_idx]
            for j in range(i + 1, min(i + 10, len(closes))):
                if direction == "long":
                    if highs[j] >= tp_price:
                        exit_price, exit_idx, hit_tp = tp_price, j, True; break
                    if lows[j] <= sl_price:
                        exit_price, exit_idx, hit_sl = sl_price, j, True; break
                else:
                    if lows[j] <= tp_price:
                        exit_price, exit_idx, hit_tp = tp_price, j, True; break
                    if highs[j] >= sl_price:
                        exit_price, exit_idx, hit_sl = sl_price, j, True; break
            pnl = (exit_price - entry_price) * units if direction == "long" else (entry_price - exit_price) * units
            pnl_pct = (pnl / pos_size) * 100 if pos_size else 0
            capital += pnl
            trades.append({
                "entry_date": dates[i], "exit_date": dates[exit_idx], "direction": direction,
                "entry_price": round(entry_price, 5), "exit_price": round(exit_price, 5),
                "target_price": round(tp_price, 5), "stop_price": round(sl_price, 5),
                "hit_target": hit_tp, "hit_stop": hit_sl, "units": round(units, 2),
                "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2),
                "capital_after": round(capital, 2), "symbol": pair,
            })
            i = exit_idx + 1
        else:
            i += 1

    metrics = _calculate_metrics(trades, initial_capital)
    run_id = str(uuid.uuid4())
    slug = strategy_slug(pair, lookback, take_profit, stop_loss, period)
    config = {"pair": pair, "period": period, "lookback": lookback,
              "momentum_threshold": momentum_threshold, "take_profit": take_profit,
              "stop_loss": stop_loss, "position_size_pct": position_size_pct,
              "initial_capital": initial_capital}
    result = {"run_id": run_id, "pair": pair, "strategy": "momentum", "strategy_slug": slug,
              "metrics": metrics, "trades": trades, "config": config,
              "initial_capital": initial_capital}
    if persist:
        try:
            _persist(result, user_id)
        except Exception as e:  # noqa: BLE001
            logger.error(f"FX backtest persist failed: {e}")
            result["persist_error"] = str(e)
    return result


def _persist(result: dict, user_id: str | None) -> None:
    run_id = result["run_id"]
    m = result["metrics"]
    slug = result["strategy_slug"]
    pair = result["pair"]
    _exec("""
        INSERT INTO assethero.runs
            (run_id, user_id, vertical, mode, strategy, strategy_slug, symbols, status,
             config, results, started_at, completed_at)
        VALUES (:rid, :uid, 'fx', 'backtest', 'momentum', :slug, :syms, 'completed',
                CAST(:cfg AS JSONB), CAST(:res AS JSONB), NOW(), NOW())
    """, {"rid": run_id, "uid": user_id, "slug": slug, "syms": [pair],
          "cfg": json.dumps(result["config"]), "res": json.dumps(m)})
    _exec("""
        INSERT INTO assethero.backtest_summaries
            (run_id, user_id, variation_index, strategy_slug, params, total_return, total_pnl,
             win_rate, total_trades, sharpe_ratio, max_drawdown, annualized_return, is_best)
        VALUES (:rid, :uid, 0, :slug, CAST(:params AS JSONB), :tr, :pnl, :wr, :nt, :sh, :dd, :ar, TRUE)
    """, {"rid": run_id, "uid": user_id, "slug": slug, "params": json.dumps(result["config"]),
          "tr": m["total_return"], "pnl": m["total_pnl"], "wr": m["win_rate"],
          "nt": m["total_trades"], "sh": m["sharpe_ratio"], "dd": m["max_drawdown"],
          "ar": m["annualized_return"]})
    for t in result["trades"]:
        _exec("""
            INSERT INTO assethero.trades
                (run_id, user_id, vertical, trade_type, strategy_slug, symbol, direction, shares,
                 entry_time, exit_time, entry_price, exit_price, target_price, stop_price,
                 hit_target, hit_stop, pnl, pnl_pct, capital_after, reason)
            VALUES (:rid, :uid, 'fx', 'backtest', :slug, :sym, :dir, :sh, :et, :xt, :ep, :xp,
                    :tp, :sp, :ht, :hs, :pnl, :pp, :ca, :reason)
        """, {"rid": run_id, "uid": user_id, "slug": slug, "sym": t["symbol"], "dir": t["direction"],
              "sh": t["units"], "et": t["entry_date"], "xt": t["exit_date"],
              "ep": t["entry_price"], "xp": t["exit_price"], "tp": t["target_price"],
              "sp": t["stop_price"], "ht": t["hit_target"], "hs": t["hit_stop"],
              "pnl": t["pnl"], "pp": t["pnl_pct"], "ca": t["capital_after"],
              "reason": f"momentum {'long' if t['direction']=='long' else 'short'}"})


# --- comparison / parameter suggestion --------------------------------------

_COMPARE_PRESETS = [
    {"label": "Conservative", "lookback": 30, "take_profit": 0.5, "stop_loss": 0.3, "period": "1y"},
    {"label": "Balanced", "lookback": 20, "take_profit": 1.0, "stop_loss": 0.5, "period": "1y"},
    {"label": "Aggressive", "lookback": 10, "take_profit": 1.5, "stop_loss": 0.8, "period": "1y"},
]

_SCENARIO_PRESETS = {
    "geopolitical_shock": {"lookback": 5, "take_profit": 2.0, "stop_loss": 1.0, "momentum_threshold": 0.3},
    "trending": {"lookback": 30, "take_profit": 2.0, "stop_loss": 0.5, "momentum_threshold": 0.5},
    "high_volatility": {"lookback": 10, "take_profit": 1.5, "stop_loss": 0.8, "momentum_threshold": 0.3},
    "range_bound": {"lookback": 5, "take_profit": 0.5, "stop_loss": 0.3, "momentum_threshold": 0.8},
    "default": {"lookback": 20, "take_profit": 1.0, "stop_loss": 0.5, "momentum_threshold": 0.5},
}


def compare_strategies(pair: str, configs: list[dict] | None = None,
                       user_id: str | None = None) -> dict:
    """Run several parameter sets on one pair; return rows for a comparison table."""
    configs = configs or _COMPARE_PRESETS
    rows = []
    for cfg in configs[:5]:
        label = cfg.get("label", "Strategy")
        r = run_momentum_backtest(
            pair=pair, period=cfg.get("period", "1y"), lookback=cfg.get("lookback", 20),
            take_profit=cfg.get("take_profit", 1.0), stop_loss=cfg.get("stop_loss", 0.5),
            user_id=user_id, persist=False,
        )
        rows.append({"label": label, "error": r.get("error"), "metrics": r.get("metrics")})
    return {"pair": pair.upper().replace("/", ""), "rows": rows}


def suggest_parameters(scenario: str, pair: str) -> dict:
    s = (scenario or "").lower()
    if any(w in s for w in ["war", "conflict", "shock", "crisis", "hormuz", "invasion", "sanctions"]):
        regime, params = "Geopolitical Shock", _SCENARIO_PRESETS["geopolitical_shock"]
    elif any(w in s for w in ["trend", "momentum", "rally", "bull", "bear"]):
        regime, params = "Trending", _SCENARIO_PRESETS["trending"]
    elif any(w in s for w in ["volatile", "uncertainty", "election", "vix"]):
        regime, params = "High Volatility", _SCENARIO_PRESETS["high_volatility"]
    elif any(w in s for w in ["range", "stable", "consolidat", "flat"]):
        regime, params = "Range-Bound", _SCENARIO_PRESETS["range_bound"]
    else:
        regime, params = "Default", _SCENARIO_PRESETS["default"]
    return {"pair": pair.upper().replace("/", ""), "regime": regime, "scenario": scenario,
            "recommended_parameters": params}


# --- HTML renderers (inline, for chat bubbles + workspace) ------------------

def _c(pos: bool) -> str:
    return "#10B981" if pos else "#EF4444"


def metrics_table_html(result: dict) -> str:
    m = result["metrics"]
    rc = _c(m["total_return"] >= 0)
    rows = [
        ("Total Return", f"<span style='color:{rc};font-weight:700'>{m['total_return']:+.2f}%</span>"),
        ("Total P&amp;L", f"<span style='color:{rc}'>${m['total_pnl']:+,.2f}</span>"),
        ("Win Rate", f"{m['win_rate']:.1f}%"),
        ("Sharpe Ratio", f"{m['sharpe_ratio']:.2f}"),
        ("Max Drawdown", f"{m['max_drawdown']:.2f}%"),
        ("Total Trades", str(m["total_trades"])),
        ("Annualized Return", f"{m['annualized_return']:+.2f}%"),
        ("Final Capital", f"${m['final_capital']:,.2f}"),
    ]
    body = "".join(f"<tr><td>{k}</td><td class='right'>{v}</td></tr>" for k, v in rows)
    return (f"<p style='font-weight:700;margin:.2rem 0'>Backtest: momentum on {result['pair']}</p>"
            f"<p class='muted' style='font-size:.72rem'>Run {result['run_id'][:8]} · "
            f"{result['strategy_slug']}</p>"
            f"<table>{body}</table>")


def trades_table_html(result: dict, limit: int = 20) -> str:
    trades = result["trades"]
    show = trades[-limit:] if len(trades) > limit else trades
    rows = ""
    for t in show:
        dc = _c(t["direction"] == "long")
        pc = _c(t["pnl"] >= 0)
        icon = "&#10003;" if t["hit_target"] else ("&#10007;" if t["hit_stop"] else "&#8212;")
        rows += (f"<tr><td>{t['entry_date']}</td>"
                 f"<td style='color:{dc};font-weight:600'>{t['direction'].upper()}</td>"
                 f"<td class='right'>{t['entry_price']:.5f}</td>"
                 f"<td class='right'>{t['exit_price']:.5f}</td>"
                 f"<td class='right' style='color:{pc}'>${t['pnl']:+,.2f}</td>"
                 f"<td class='right' style='color:{pc}'>{t['pnl_pct']:+.2f}%</td>"
                 f"<td>{icon}</td></tr>")
    caption = f"Trade log ({len(trades)} trades" + (", last 20" if len(trades) > limit else "") + ")"
    return (f"<p style='font-weight:600;margin:.6rem 0 .3rem'>{caption}</p>"
            f"<table><thead><tr><th>Date</th><th>Dir</th><th class='right'>Entry</th>"
            f"<th class='right'>Exit</th><th class='right'>P&amp;L</th>"
            f"<th class='right'>P&amp;L%</th><th>Hit</th></tr></thead><tbody>{rows}</tbody></table>")


def equity_curve_html(result: dict, div_id: str = "fx-bt-equity") -> str:
    trades = result["trades"]
    if len(trades) < 2:
        return ""
    caps = [result["initial_capital"]] + [t["capital_after"] for t in trades]
    dts = ["Start"] + [t["exit_date"] for t in trades]
    return build_equity_curve_html(dts, caps, positive=result["metrics"]["total_return"] >= 0,
                                   div_id=div_id, title=f"Equity Curve — {result['pair']}")


def compare_table_html(comp: dict) -> str:
    rows = ""
    for r in comp["rows"]:
        if r.get("error"):
            rows += f"<tr><td>{r['label']}</td><td colspan='5' class='muted'>{r['error']}</td></tr>"
        else:
            m = r["metrics"]
            rc = _c(m["total_return"] >= 0)
            rows += (f"<tr><td>{r['label']}</td>"
                     f"<td class='right' style='color:{rc}'>{m['total_return']:+.2f}%</td>"
                     f"<td class='right'>{m['sharpe_ratio']:.2f}</td>"
                     f"<td class='right'>{m['max_drawdown']:.2f}%</td>"
                     f"<td class='right'>{m['win_rate']:.1f}%</td>"
                     f"<td class='right'>{m['total_trades']}</td></tr>")
    return (f"<p style='font-weight:700;margin:.2rem 0'>Strategy comparison: {comp['pair']}</p>"
            f"<table><thead><tr><th>Strategy</th><th class='right'>Return</th>"
            f"<th class='right'>Sharpe</th><th class='right'>Max DD</th>"
            f"<th class='right'>Win</th><th class='right'>Trades</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>")
