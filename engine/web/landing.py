"""AssetHero marketing landing — liquidround-style Tailwind house style.

Public, DB-free pages: `/` (home), `/asset-classes`, `/how-it-works`, `/pricing`,
`/contact`. Dark-navy palette + amber accents, shared with the in-app shell
(engine/web/layout.py uses the same hex tokens).
"""
from __future__ import annotations

from fasthtml.common import (
    A, Button, Div, Form, H1, H2, H3, Img, Input, Li, Link, Main, Meta, P,
    Script, Span, Style, Title, Ul, NotStr,
)

# ───── Palette (shared with layout.py) ──────────────────────────────────
BG        = "#0B1220"   # deep navy
BG_ELEV   = "#111A2E"   # elevated panels
INK       = "#E5E7EB"   # near-white text
INK_MUTED = "#94A3B8"   # slate-400
CTA       = "#F59E0B"   # amber-500 accent / brand
LINE      = "#1E293B"   # slate-800

# ───── Asset-class registry (drives pillars + landing switcher) ─────────
# (key, name, icon, accent, tagline, blurb, status)
ASSET_CLASSES = [
    ("equities", "Equities", "📈", "#3B82F6", "US stocks & ETFs · Alpaca",
     "Grid-search backtests, paper trading, and live reconciliation on the "
     "Alpaca paper API. Buy-the-Dip, VIX, Momentum and Box-Wedge strategies "
     "with PDT-rule enforcement.", "live"),
    ("crypto", "Crypto", "🪙", "#F59E0B", "24/7 digital assets",
     "Multi-agent RL swarm for spot and perp markets — momentum, mean-reversion "
     "and market-making agents backtested on the same engine.", "soon"),
    ("fx", "FX / Macro", "💱", "#10B981", "Currencies & rates",
     "Macro-driven FX and rates signals — carry, trend and macro-regime models "
     "with economic-calendar awareness.", "soon"),
    ("prediction", "Prediction Markets", "🔮", "#8B5CF6", "Event & binary outcomes",
     "Polymarket-style event contracts — probability edges, arbitrage across "
     "venues, and resolution-aware position sizing.", "soon"),
    ("research", "Research", "🔬", "#06B6D4", "Equity & alpha research",
     "Multi-agent fundamental and quant research — factor screens, filings "
     "analysis and thesis drafting that feeds every trading vertical.", "soon"),
]

STRATEGIES = [
    ("Buy the Dip", "btd", "Buys on dip-threshold drops, exits at take-profit, stop-loss or hold-days."),
    ("VIX Fear Index", "vix", "Trades when the VIX exceeds a threshold — fear as signal."),
    ("Momentum", "mom", "Buys strong upward momentum over a configurable lookback."),
    ("Box-Wedge", "bwg", "Pattern-based breakouts from consolidation ranges."),
]


# ───── Shared chrome ────────────────────────────────────────────────────

_DESC = ("AssetHero — one AI engine to backtest and paper-trade every asset class: "
         "equities, crypto, FX/macro, prediction markets and research.")


def landing_head(title: str = "AssetHero", description: str | None = None):
    desc = description or _DESC
    return (
        Title(title),
        Meta(charset="utf-8"),
        Meta(name="viewport", content="width=device-width, initial-scale=1"),
        Meta(name="theme-color", content=BG),
        Meta(name="description", content=desc),
        Meta(property="og:type", content="website"),
        Meta(property="og:site_name", content="AssetHero"),
        Meta(property="og:title", content=title),
        Meta(property="og:description", content=desc),
        Script(src="https://cdn.tailwindcss.com"),
        Link(rel="preconnect", href="https://fonts.googleapis.com"),
        Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
        Link(href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap",
             rel="stylesheet"),
        Style(f"""
            html {{ overflow-x: hidden; scrollbar-width: none; scroll-behavior: smooth; }}
            html::-webkit-scrollbar {{ display: none; }}
            html, body {{ background: {BG}; color: {INK}; margin: 0;
                font-family: 'Inter', system-ui, sans-serif; letter-spacing: -0.01em; }}
            .mono {{ font-family: 'JetBrains Mono', ui-monospace, monospace; }}
            .tighter {{ letter-spacing: -0.025em; }}
            .tightest {{ letter-spacing: -0.04em; }}
            .hero-gradient {{ background: radial-gradient(ellipse 80% 50% at 50% 0%,
                rgba(245,158,11,0.12), transparent 70%); }}
            .cta-glow {{ box-shadow: 0 0 40px rgba(245,158,11,0.30); }}
            a {{ transition: color .15s ease, opacity .15s ease; }}
            .nav-link:hover {{ color: {CTA}; }}
            .card {{ background: {BG_ELEV}; border: 1px solid {LINE}; transition: border-color .15s ease; }}
            .card:hover {{ border-color: {CTA}; }}
        """),
    )


def landing_nav(active: str = "home"):
    def link(href, label, key):
        cls = "text-sm nav-link " + ("text-white font-medium" if key == active else "text-slate-400")
        return A(label, href=href, cls=cls)

    nav_items = [
        ("assets", "/asset-classes", "Asset Classes"),
        ("how", "/how-it-works", "How it works"),
        ("pricing", "/pricing", "Pricing"),
    ]

    bar = "block w-5 h-0.5 mb-1"
    hamburger = Button(
        Span(cls=bar, style=f"background:{INK};"),
        Span(cls=bar, style=f"background:{INK};"),
        Span(cls="block w-5 h-0.5", style=f"background:{INK};"),
        cls="lg:hidden flex flex-col justify-center items-center p-2 bg-transparent border-none cursor-pointer",
        aria_label="Open menu",
        onclick="document.getElementById('mobile-menu').classList.toggle('hidden')",
    )
    mobile_links = [A(l, href=h, cls="block px-4 py-3 text-sm no-underline", style=f"color:{INK_MUTED};")
                    for _k, h, l in nav_items]
    mobile_links.append(A("Sign in", href="/login", cls="block px-4 py-3 text-sm font-medium no-underline",
                          style=f"color:{CTA};"))
    mobile_menu = Div(*mobile_links, id="mobile-menu", cls="hidden lg:hidden",
                      style=f"background:{BG_ELEV}; border-top:1px solid {LINE};")

    return Div(
        Div(
            A(Div(Span("◆", cls="text-xl mr-2", style=f"color:{CTA}"),
                  Span("Asset", cls="text-base font-semibold tighter"),
                  Span("Hero", cls="text-base font-semibold tighter", style=f"color:{CTA}"),
                  cls="flex items-center"),
              href="/", cls="text-white no-underline"),
            Div(*[link(h, l, k) for k, h, l in nav_items],
                cls="hidden lg:flex items-center gap-6"),
            Div(
                A("Sign in", href="/login",
                  cls="hidden sm:inline-flex text-sm px-3 py-1.5 rounded-md font-medium no-underline",
                  style=f"background:{BG_ELEV}; color:{INK}; border:1px solid {LINE};"),
                A("Launch app →", href="/equities",
                  cls="hidden sm:inline-flex text-sm px-3 py-1.5 rounded-md font-semibold text-white no-underline ml-2",
                  style=f"background:{CTA};"),
                hamburger,
                cls="flex items-center gap-2",
            ),
            cls="max-w-6xl mx-auto flex items-center justify-between px-4 sm:px-6 py-4",
        ),
        mobile_menu,
        cls="border-b sticky top-0 z-40 backdrop-blur",
        style=f"border-color:{LINE}; background: rgba(11,18,32,0.85);",
    )


def landing_footer():
    return Div(
        Div(
            Div(Span("◆ ", style=f"color:{CTA}"),
                Span("AssetHero", cls="text-sm font-semibold tighter"),
                Span("© 2026 Predictive Labs Ltd.", cls="ml-3 text-xs text-slate-500"),
                cls="flex items-center"),
            Div(
                A("Asset Classes", href="/asset-classes", cls="text-xs text-slate-400 nav-link"),
                Span("·", cls="text-xs text-slate-600 mx-2"),
                A("How it works", href="/how-it-works", cls="text-xs text-slate-400 nav-link"),
                Span("·", cls="text-xs text-slate-600 mx-2"),
                A("Pricing", href="/pricing", cls="text-xs text-slate-400 nav-link"),
                Span("·", cls="text-xs text-slate-600 mx-2"),
                A("Contact", href="/contact", cls="text-xs text-slate-400 nav-link"),
                cls="flex items-center flex-wrap gap-y-1 justify-center sm:justify-end"),
            cls="max-w-6xl mx-auto px-4 sm:px-6 py-6 flex flex-col sm:flex-row items-center justify-between gap-3",
        ),
        cls="border-t mt-20", style=f"border-color:{LINE};",
    )


# ───── Home-page sections ───────────────────────────────────────────────

def hero():
    return Div(
        Div(
            Div(
                Span("◆", cls="mono mr-2", style=f"color:{CTA}"),
                Span("One engine · every asset class",
                     cls="text-xs mono uppercase tracking-widest", style=f"color:{INK_MUTED}"),
                cls="flex items-center justify-center mb-6 md:mb-8",
            ),
            H1(
                Span("Backtest and paper-trade "),
                Span("every market", style=f"color:{CTA};"),
                Span(" with one AI engine."),
                cls="text-3xl sm:text-4xl md:text-5xl lg:text-6xl font-bold tightest text-center mb-4 md:mb-6",
                style=f"color:{INK};",
            ),
            P(
                Span("A shared backtesting and paper-trading engine across ",
                     style=f"color:{INK_MUTED};"),
                Span("equities", style="color:#3B82F6;"),
                Span(", ", style=f"color:{INK_MUTED};"),
                Span("crypto", style="color:#F59E0B;"),
                Span(", ", style=f"color:{INK_MUTED};"),
                Span("FX / macro", style="color:#10B981;"),
                Span(", ", style=f"color:{INK_MUTED};"),
                Span("prediction markets", style="color:#8B5CF6;"),
                Span(" and ", style=f"color:{INK_MUTED};"),
                Span("research", style="color:#06B6D4;"),
                Span(". Same methodology, same metrics, one workspace.",
                     style=f"color:{INK_MUTED};"),
                cls="text-base md:text-lg lg:text-xl text-center max-w-3xl mx-auto mb-8 md:mb-10 leading-relaxed px-2",
            ),
            Div(
                A(Span("Launch the app"), Span(" →", cls="ml-2"),
                  href="/equities",
                  cls="cta-glow rounded-lg px-6 py-3 inline-flex items-center text-white no-underline font-semibold",
                  style=f"background:{CTA};"),
                A("Explore asset classes", href="/asset-classes",
                  cls="rounded-lg px-6 py-3 inline-flex items-center no-underline font-semibold",
                  style=f"background:{BG_ELEV}; color:{INK}; border:1px solid {LINE};"),
                cls="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 mb-4",
            ),
            P("Equities is live on the Alpaca paper API. Other verticals are rolling out.",
              cls="text-center text-xs mb-4", style=f"color:{INK_MUTED};"),
            cls="max-w-4xl mx-auto px-4 sm:px-6 pt-12 md:pt-20 pb-10 md:pb-12 text-center",
        ),
        cls="hero-gradient",
    )


def stats_bar():
    items = [
        ("5", "asset classes"),
        ("1", "shared engine"),
        ("4", "equity strategies live"),
        ("Paper", "trade before you risk"),
    ]
    return Div(
        Div(*[Div(Div(v, cls="text-2xl font-bold tightest", style=f"color:{INK};"),
                  Div(l, cls="text-xs mono uppercase tracking-widest mt-1", style=f"color:{INK_MUTED};"),
                  cls="text-center") for v, l in items],
            cls="grid grid-cols-2 md:grid-cols-4 gap-6 md:gap-8 max-w-4xl mx-auto px-4 sm:px-6 py-10 md:py-12"),
        cls="border-y", style=f"border-color:{LINE};",
    )


def _status_badge(status: str, accent: str):
    if status == "live":
        return Span("● Live", cls="text-[10px] mono uppercase tracking-widest px-2 py-0.5 rounded",
                    style=f"color:{accent}; border:1px solid {accent};")
    return Span("Soon", cls="text-[10px] mono uppercase tracking-widest px-2 py-0.5 rounded",
                style=f"color:{INK_MUTED}; border:1px solid {LINE};")


def asset_pillar(key, name, icon, accent, tagline, blurb, status):
    href = "/equities" if status == "live" else "/asset-classes"
    return A(
        Div(
            Div(Span(icon, cls="text-3xl"),
                _status_badge(status, accent),
                cls="flex items-center justify-between mb-3"),
            H3(name, cls="text-base font-semibold tighter", style=f"color:{INK};"),
            P(tagline, cls="text-xs mono uppercase tracking-widest mt-1", style=f"color:{accent};"),
            P(blurb, cls="text-sm mt-3 leading-relaxed", style=f"color:{INK_MUTED};"),
            cls="card rounded-lg p-5 h-full",
        ),
        href=href, cls="no-underline block",
    )


def pillars_section(heading=True):
    body = []
    if heading:
        body += [
            H2("Five markets. One playbook.",
               cls="text-3xl md:text-4xl font-bold tightest text-center mb-4", style=f"color:{INK};"),
            P("Every vertical runs on the same backtest → validate → paper-trade → report loop.",
              cls="text-center mb-12", style=f"color:{INK_MUTED};"),
        ]
    return Div(
        Div(
            *body,
            Div(*[asset_pillar(*ac) for ac in ASSET_CLASSES],
                cls="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"),
            cls="max-w-6xl mx-auto px-4 sm:px-6 py-14 md:py-20",
        ),
    )


def how_it_works_section():
    steps = [
        ("1. Backtest", "Grid-search parameterised strategies over historical data with the shared engine. Every run is stored with a compact strategy slug and full metrics.", "#3B82F6"),
        ("2. Validate", "A validator agent cross-checks trades against market data in a self-correction loop before anything goes live.", CTA),
        ("3. Paper-trade & report", "Promote a strategy to live paper trading via the broker API, reconcile positions, and get summaries of top strategies and run details.", "#10B981"),
    ]
    return Div(
        Div(
            H2("From idea to paper trade — one loop.",
               cls="text-3xl md:text-4xl font-bold tightest text-center mb-12", style=f"color:{INK};"),
            Div(*[Div(Div(label.split(".")[0] + ".", cls="text-4xl font-bold tightest mb-3", style=f"color:{color};"),
                      H3(label.split(". ", 1)[1], cls="text-lg font-semibold tighter mb-2", style=f"color:{INK};"),
                      P(body, cls="text-sm leading-relaxed", style=f"color:{INK_MUTED};"),
                      cls="card rounded-lg p-6") for label, body, color in steps],
                cls="grid grid-cols-1 md:grid-cols-3 gap-4"),
            cls="max-w-6xl mx-auto px-4 sm:px-6 py-14 md:py-20",
        ),
    )


def cta_section():
    return Div(
        Div(
            H2("Every asset class. One workspace.",
               cls="text-3xl md:text-4xl font-bold tightest text-center mb-4", style=f"color:{INK};"),
            P("Sign in, pick a vertical, and start backtesting.",
              cls="text-center mb-10", style=f"color:{INK_MUTED};"),
            Div(
                A("Launch the app →", href="/equities",
                  cls="cta-glow rounded-lg px-6 py-3 text-base font-semibold text-white no-underline",
                  style=f"background:{CTA};"),
                A("Sign in", href="/login",
                  cls="rounded-lg px-6 py-3 text-base font-semibold no-underline",
                  style=f"background:{BG_ELEV}; color:{INK}; border:1px solid {LINE};"),
                cls="flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4",
            ),
            cls="max-w-4xl mx-auto px-4 sm:px-6 py-14 md:py-20 text-center",
        ),
    )


# ───── Page shell + concrete pages ──────────────────────────────────────

def landing_page(*sections, active: str = "home", title: str = "AssetHero",
                  description: str | None = None):
    return (
        *landing_head(title, description=description),
        landing_nav(active=active),
        Main(*sections),
        landing_footer(),
    )


def home_page():
    return landing_page(
        hero(), stats_bar(), pillars_section(), how_it_works_section(), cta_section(),
        active="home",
        title="AssetHero — Backtest & paper-trade every asset class",
    )


def asset_classes_page():
    return landing_page(
        Div(
            Div(
                Span("◆", cls="mono mr-2", style=f"color:{CTA}"),
                Span("5 verticals · one shared engine",
                     cls="text-xs mono uppercase tracking-widest", style=f"color:{INK_MUTED}"),
                cls="flex items-center justify-center mb-6 pt-16 md:pt-20",
            ),
            H1("Asset classes.", cls="text-4xl md:text-5xl font-bold tightest text-center mb-4",
               style=f"color:{INK};"),
            P("The same backtesting methodology and metrics, specialised per market. Equities is live today; the rest are being merged into the monorepo vertical by vertical.",
              cls="text-lg text-center max-w-2xl mx-auto mb-4", style=f"color:{INK_MUTED};"),
            cls="max-w-4xl mx-auto px-6",
        ),
        pillars_section(heading=False),
        # Equities strategy detail
        Div(
            Div(
                H2("Live now: Equities strategies.",
                   cls="text-2xl font-bold tightest text-center mb-3", style=f"color:{INK};"),
                P("Parameterised, slug-encoded, PDT-aware — running on the Alpaca paper API.",
                  cls="text-sm text-center mb-10", style=f"color:{INK_MUTED};"),
                Div(*[Div(
                        Div(Span(name, cls="text-sm font-semibold", style=f"color:{INK};"),
                            Span(slug, cls="mono text-xs ml-2 px-1.5 py-0.5 rounded",
                                 style=f"color:{CTA}; border:1px solid {LINE};"),
                            cls="flex items-center"),
                        P(desc, cls="text-xs mt-2 leading-relaxed", style=f"color:{INK_MUTED};"),
                        cls="card rounded-lg p-4")
                      for name, slug, desc in STRATEGIES],
                    cls="grid grid-cols-1 md:grid-cols-2 gap-4"),
                cls="max-w-4xl mx-auto px-6 py-16",
            ),
        ),
        cta_section(),
        active="assets", title="Asset Classes — AssetHero",
    )


def how_it_works_page():
    return landing_page(
        Div(
            H1("How it works.", cls="text-4xl md:text-5xl font-bold tightest text-center pt-16 md:pt-20 mb-4",
               style=f"color:{INK};"),
            P("Backtest, validate, paper-trade, report — coordinated by a multi-agent orchestrator.",
              cls="text-center mb-8", style=f"color:{INK_MUTED};"),
        ),
        how_it_works_section(),
        cta_section(),
        active="how", title="How it works — AssetHero",
    )


def pricing_page():
    tiers = [
        ("Explorer", "Free", "Backtest and paper-trade on your own keys.",
         ["Full backtesting engine", "Equities paper trading", "Bring your own Alpaca keys", "Strategy slugs & metrics"], False),
        ("Pro", "From $49 / month", "For active multi-strategy traders.",
         ["Everything in Explorer", "All asset classes as they launch", "Validation & reconciliation agents", "Priority data feeds", "Email support"], True),
        ("Enterprise", "Contact us", "For desks and funds.",
         ["Everything in Pro", "SSO + audit logs", "Custom strategies & agents", "Dedicated infra", "SLA"], False),
    ]
    return landing_page(
        Div(
            H1("Start free. Scale when it works.",
               cls="text-4xl md:text-5xl font-bold tightest text-center pt-16 md:pt-20 mb-4", style=f"color:{INK};"),
            P("Paper-trade everything before you risk a cent.",
              cls="text-center mb-16", style=f"color:{INK_MUTED};"),
            Div(*[Div(
                    (Div(Span("MOST POPULAR", cls="mono text-[10px] tracking-widest px-2 py-0.5 rounded"),
                         style=f"color:{BG}; background:{CTA};", cls="inline-block mb-3") if hl else ""),
                    H3(name, cls="text-lg font-semibold tighter", style=f"color:{INK};"),
                    Div(price, cls="text-3xl font-bold tightest my-3", style=f"color:{INK};"),
                    P(desc, cls="text-sm mb-5", style=f"color:{INK_MUTED};"),
                    Ul(*[Li(f"✓ {i}", cls="text-sm py-1", style=f"color:{INK};") for i in items],
                       cls="list-none pl-0 mb-6"),
                    A("Get started →", href="/login",
                      cls="block text-center rounded-lg px-4 py-2 text-sm font-semibold text-white no-underline",
                      style=f"background:{CTA if hl else LINE};"),
                    cls="card rounded-lg p-6" + (" ring-2" if hl else ""),
                    style=(f"border-color:{CTA}" if hl else ""))
                  for name, price, desc, items, hl in tiers],
                cls="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-5xl mx-auto px-6 pb-20"),
        ),
        active="pricing", title="Pricing — AssetHero",
    )


# ───── Auth shell (login / register) ────────────────────────────────────

_GOOGLE_SVG = ('<svg width="18" height="18" viewBox="0 0 18 18">'
    '<path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.615z" fill="#4285F4"/>'
    '<path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z" fill="#34A853"/>'
    '<path d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 000 9s.38 1.572.957 3.042l3.007-2.332z" fill="#FBBC05"/>'
    '<path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/></svg>')


def google_btn(label: str):
    return A(NotStr(_GOOGLE_SVG), Span(label, cls="ml-2"),
            href="/auth/google",
            cls="flex items-center justify-center w-full py-2.5 rounded-lg font-semibold text-sm no-underline",
            style=f"background:{BG_ELEV}; color:{INK}; border:1px solid {LINE};")


def auth_input(name, placeholder, itype="text", **kw):
    return Input(type=itype, name=name, placeholder=placeholder,
                 cls="w-full rounded-lg px-3 py-2.5 text-sm focus:outline-none",
                 style=f"background:{BG}; color:{INK}; border:1px solid {LINE};", **kw)


def auth_submit(label):
    return Button(label, type="submit",
                  cls="w-full text-white py-2.5 rounded-lg font-semibold text-sm cursor-pointer",
                  style=f"background:{CTA};")


def _auth_divider():
    return Div(Div(cls="flex-1 h-px", style=f"background:{LINE};"),
               Span("or", cls="px-3 text-xs", style=f"color:{INK_MUTED};"),
               Div(cls="flex-1 h-px", style=f"background:{LINE};"),
               cls="flex items-center my-4")


def auth_page(*card_parts, title: str = "Sign in", subtitle: str = "Multi-asset trading platform"):
    return (
        *landing_head(f"{title} — AssetHero"),
        Main(
            Div(
                A(Div(Span("◆", cls="text-3xl", style=f"color:{CTA};"),
                      P(Span("Asset"), Span("Hero", style=f"color:{CTA}"),
                        cls="text-xl font-bold mt-2", style=f"color:{INK};"),
                      P(subtitle, cls="text-xs", style=f"color:{INK_MUTED};"),
                      cls="text-center mb-6"), href="/", cls="no-underline"),
                Div(*card_parts, cls="w-full max-w-sm rounded-xl p-8 shadow-lg",
                    style=f"background:{BG_ELEV}; border:1px solid {LINE};"),
                P("Predictive Labs Ltd", cls="text-xs mt-6", style=f"color:#475569;"),
                cls="flex flex-col items-center justify-center min-h-screen px-4",
            ),
            style=f"background:{BG};",
        ),
    )


def auth_error(msg: str):
    return Div(msg, cls="text-sm px-3 py-2 rounded-lg text-center mb-3",
               style="color:#EF4444; background:rgba(239,68,68,0.1);") if msg else ""


def contact_page():
    return landing_page(
        Div(
            H1("Talk to us.", cls="text-4xl md:text-5xl font-bold tightest text-center pt-16 md:pt-20 mb-4",
               style=f"color:{INK};"),
            P("Predictive Labs Ltd — ",
              A("hello@predictivelabs.ai", href="mailto:hello@predictivelabs.ai", style=f"color:{CTA};"),
              cls="text-center mb-16", style=f"color:{INK_MUTED};"),
            Div(
                P("AssetHero is a multi-asset trading platform built on a shared backtesting and paper-trading engine.",
                  cls="text-sm mb-4", style=f"color:{INK_MUTED};"),
                P("For access, partnerships, or engineering roles — drop a line.",
                  cls="text-sm", style=f"color:{INK_MUTED};"),
                cls="max-w-xl mx-auto px-6 pb-20 text-center card rounded-lg p-8 mt-8"),
        ),
        active="contact", title="Contact — AssetHero",
    )
