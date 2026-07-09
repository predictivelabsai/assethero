"""FX + Treasury market data and Plotly chart builders for the FX vertical.

- FX spot history via yfinance (lazy import).
- US Treasury yield-rates via EODHD (key resolved through engine.integrations).
- Self-contained Plotly HTML chart builders (CDN Plotly), themed to the
  assethero dark house style. Each chart takes a unique ``div_id`` so several
  charts can coexist on one page.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# House-style chart tokens (match engine/web/layout.py LAYOUT_CSS).
_PAPER = "#111A2E"
_PLOT = "#0f1830"
_GRID = "#1E293B"
_FONT = "#94A3B8"
_ACCENT = "#F59E0B"   # amber
_ACCENT2 = "#10B981"  # green
_INFO = "#3B82F6"     # blue
_DANGER = "#EF4444"   # red
_PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"


# --- data fetchers ----------------------------------------------------------

def get_fx_history(pair: str, period: str = "1y") -> dict:
    """FX close history via yfinance. Returns {pair, dates, rates}."""
    from .config import yf_ticker
    import yfinance as yf
    ticker = yf_ticker(pair)
    try:
        data = yf.Ticker(ticker).history(period=period)
        if data.empty:
            return {"pair": pair, "dates": [], "rates": []}
        dates = [d.strftime("%Y-%m-%d") for d in data.index]
        rates = [round(float(r), 5) for r in data["Close"].values]
        return {"pair": pair, "dates": dates, "rates": rates}
    except Exception as e:  # noqa: BLE001
        logger.error(f"yfinance error for {pair}: {e}")
        return {"pair": pair, "dates": [], "rates": []}


def get_fx_ohlc(pair: str, period: str = "1y", interval: str = "1d") -> dict:
    """FX OHLC history via yfinance. Returns {dates, closes, highs, lows}."""
    from .config import yf_ticker
    import yfinance as yf
    ticker = yf_ticker(pair)
    try:
        data = yf.Ticker(ticker).history(period=period, interval=interval)
        if data.empty:
            return {"dates": [], "closes": [], "highs": [], "lows": []}
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in data.index],
            "closes": [float(c) for c in data["Close"].values],
            "highs": [float(h) for h in data["High"].values],
            "lows": [float(l) for l in data["Low"].values],
        }
    except Exception as e:  # noqa: BLE001
        logger.error(f"yfinance OHLC error for {pair}: {e}")
        return {"dates": [], "closes": [], "highs": [], "lows": []}


def analyze_pair(pair: str, period: str = "5d") -> dict:
    """Quick spot snapshot for a pair (current, change, high/low)."""
    hist = get_fx_ohlc(pair, period=period)
    closes = hist.get("closes") or []
    if not closes:
        return {"pair": pair.upper(), "error": f"No data for {pair}"}
    first, last = closes[0], closes[-1]
    change = last - first
    return {
        "pair": pair.upper().replace("/", ""),
        "current": round(last, 5),
        "open": round(first, 5),
        "change": round(change, 5),
        "change_pct": round((change / first) * 100, 3) if first else 0.0,
        "high": round(max(hist["highs"]), 5) if hist.get("highs") else None,
        "low": round(min(hist["lows"]), 5) if hist.get("lows") else None,
        "period": period,
    }


def get_treasury_yields(api_key: str, year: int | None = None) -> list[dict]:
    """Fetch US Treasury yield rates for one year from EODHD (synchronous)."""
    if not api_key:
        return []
    import requests
    if year is None:
        year = datetime.now().year
    url = "https://eodhd.com/api/ust/yield-rates"
    params = {"api_token": api_key, "filter[year]": year, "fmt": "json"}
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception as e:  # noqa: BLE001
        logger.error(f"EODHD yield rates error: {e}")
        return []


def get_treasury_yields_multi_year(api_key: str, years: int = 1) -> list[dict]:
    current = datetime.now().year
    out: list[dict] = []
    for y in range(current - years + 1, current + 1):
        out.extend(get_treasury_yields(api_key, y))
    return out


def treasury_10y_series(rows: list[dict]) -> tuple[list[str], list[float]]:
    """Extract (dates, 10Y yields) from EODHD yield-rate rows."""
    dates, yields = [], []
    for row in rows:
        d = row.get("date") or row.get("Date") or ""
        y10 = row.get("10 Yr") or row.get("10Yr") or row.get("d10")
        if d and y10 is not None:
            try:
                yields.append(float(y10))
                dates.append(d)
            except (ValueError, TypeError):
                continue
    return dates, yields


# --- Plotly chart builders (dark house style) -------------------------------

def _layout(title: str, y_label: str = "", extra: str = "") -> str:
    return (
        f"title:{{text:{json.dumps(title)},font:{{color:'#E5E7EB',size:13}}}},"
        f"font:{{size:11,color:'{_FONT}'}},"
        f"margin:{{l:60,r:60,t:44,b:40}},"
        f"paper_bgcolor:'{_PAPER}',plot_bgcolor:'{_PLOT}',"
        f"xaxis:{{showgrid:true,gridcolor:'{_GRID}',linecolor:'{_GRID}'}},"
        f"yaxis:{{title:{json.dumps(y_label)},showgrid:true,gridcolor:'{_GRID}',linecolor:'{_GRID}'}},"
        f"{extra}"
    )


def build_line_chart_html(title: str, dates: list, values: list, series_name: str,
                          y_label: str = "", color: str = _INFO, div_id: str = "fx-line") -> str:
    return f"""<div id="{div_id}" style="width:100%;height:340px;"></div>
<script src="{_PLOTLY_CDN}"></script>
<script>
Plotly.newPlot('{div_id}', [{{
  x:{json.dumps(dates)}, y:{json.dumps(values)}, name:{json.dumps(series_name)},
  type:'scatter', mode:'lines', line:{{color:'{color}',width:2}},
  fill:'tozeroy', fillcolor:'{color}22'
}}], {{{_layout(title, y_label)}}}, {{responsive:true,displayModeBar:false}});
</script>"""


def build_dual_axis_chart_html(title: str, dates: list, s1: list, s1_name: str,
                               s2: list, s2_name: str, y1_label: str = "", y2_label: str = "",
                               div_id: str = "fx-dual") -> str:
    extra = (
        f"yaxis:{{title:{json.dumps(y1_label)},titlefont:{{color:'{_INFO}'}},tickfont:{{color:'{_INFO}'}},"
        f"showgrid:true,gridcolor:'{_GRID}'}},"
        f"yaxis2:{{title:{json.dumps(y2_label)},titlefont:{{color:'{_ACCENT}'}},tickfont:{{color:'{_ACCENT}'}},"
        f"overlaying:'y',side:'right'}},"
        f"legend:{{x:0,y:1.14,orientation:'h',font:{{color:'{_FONT}'}}}}"
    )
    base = (
        f"title:{{text:{json.dumps(title)},font:{{color:'#E5E7EB',size:13}}}},"
        f"font:{{size:11,color:'{_FONT}'}},margin:{{l:60,r:60,t:50,b:40}},"
        f"paper_bgcolor:'{_PAPER}',plot_bgcolor:'{_PLOT}',"
        f"xaxis:{{showgrid:true,gridcolor:'{_GRID}',linecolor:'{_GRID}'}},"
    )
    return f"""<div id="{div_id}" style="width:100%;height:400px;"></div>
<script src="{_PLOTLY_CDN}"></script>
<script>
Plotly.newPlot('{div_id}', [
  {{x:{json.dumps(dates)},y:{json.dumps(s1)},name:{json.dumps(s1_name)},type:'scatter',mode:'lines',
    line:{{color:'{_INFO}',width:2}},yaxis:'y'}},
  {{x:{json.dumps(dates)},y:{json.dumps(s2)},name:{json.dumps(s2_name)},type:'scatter',mode:'lines',
    line:{{color:'{_ACCENT}',width:2}},yaxis:'y2'}}
], {{{base}{extra}}}, {{responsive:true,displayModeBar:false}});
</script>"""


def build_equity_curve_html(dates: list, capitals: list, positive: bool = True,
                            div_id: str = "fx-equity", title: str = "Equity Curve") -> str:
    color = _ACCENT2 if positive else _DANGER
    return f"""<div id="{div_id}" style="width:100%;height:300px;"></div>
<script src="{_PLOTLY_CDN}"></script>
<script>
Plotly.newPlot('{div_id}', [{{
  x:{json.dumps(dates)}, y:{json.dumps(capitals)}, type:'scatter', mode:'lines',
  line:{{color:'{color}',width:2}}, fill:'tozeroy', fillcolor:'{color}22', name:'Equity'
}}], {{{_layout(title, 'Capital ($)')}}}, {{responsive:true,displayModeBar:false}});
</script>"""


def merge_treasury_fx(t_dates: list, t_yields: list, fx_dates: list, fx_rates: list):
    """Forward-fill align two date series to a common calendar for a dual chart."""
    if not t_dates or not fx_dates:
        return [], [], []
    common_start = max(t_dates[0], fx_dates[0])
    t_f = [(d, y) for d, y in zip(t_dates, t_yields) if d >= common_start]
    fx_f = [(d, r) for d, r in zip(fx_dates, fx_rates) if d >= common_start]
    if not t_f or not fx_f:
        return [], [], []
    all_dates = sorted(set(d for d, _ in t_f) | set(d for d, _ in fx_f))
    t_map, fx_map = dict(t_f), dict(fx_f)
    out_d, out_t, out_fx = [], [], []
    last_t, last_fx = t_f[0][1], fx_f[0][1]
    for d in all_dates:
        last_t = t_map.get(d, last_t)
        last_fx = fx_map.get(d, last_fx)
        out_d.append(d)
        out_t.append(last_t)
        out_fx.append(last_fx)
    return out_d, out_t, out_fx
