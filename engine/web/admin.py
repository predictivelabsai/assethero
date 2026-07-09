"""Admin / Integrations — per-user API-key management page.

Renders Trading Platforms + Data Sources as provider cards; saves keys
Fernet-encrypted (never echoing stored secret values back to the browser).
Mounted by app.py via `register(app, rt, current_user)`.
"""
from __future__ import annotations

from fasthtml.common import (
    A, Button, Div, Form, H2, H3, Input, Label, P, Span, NotStr,
)
from starlette.responses import RedirectResponse

from engine.web.layout import settings_page
from engine import integrations as I


def _status_pill(state: dict):
    if not state:
        return Span("not set", cls="st")
    st = state.get("status", "unknown")
    if st == "ok":
        return Span("● connected", cls="st ok")
    if st == "error":
        return Span("error", cls="st error")
    if state.get("configured"):
        return Span("set", cls="st set")
    return Span("not set", cls="st")


def _provider_card(prov, state: dict):
    configured = bool(state.get("configured"))
    fields = []
    for f in prov.fields:
        ph = "•••••••• (set — leave blank to keep)" if (configured and f.secret) else f.label
        fields.append(Label(f.label))
        fields.append(Input(name=f.key, type=("password" if f.secret else "text"),
                            placeholder=ph, autocomplete="off"))
    return Div(
        Div(Span(prov.name, cls="nm"), _status_pill(state), cls="hd"),
        P(prov.help, cls="help"),
        Form(
            *fields,
            Div(
                Button("Save", type="submit", cls="btn"),
                Button("Test", type="submit", cls="btn ghost",
                       formaction=f"/admin/integrations/{prov.key}/test"),
                cls="acts",
            ),
            method="post", action=f"/admin/integrations/{prov.key}",
        ),
        cls="intcard",
    )


def _page(user, flash: str = ""):
    state = I.summary(user["user_id"])
    blocks = [H2("Integrations"),
              P("Connect your brokers, exchanges, wallets and data providers. "
                "Keys are encrypted at rest and never leave your account.", cls="sub")]
    if flash:
        blocks.append(Div(flash, cls="flash"))
    blocks.append(Div("Trading Platforms", cls="navhead2"))
    blocks.append(Div(*[_provider_card(p, state.get(p.key, {})) for p in I.TRADING], cls="intgrid"))
    blocks.append(Div("Data Sources", cls="navhead2"))
    blocks.append(Div(*[_provider_card(p, state.get(p.key, {})) for p in I.DATA], cls="intgrid"))
    return settings_page("equities", [("Dashboard", "/equities")], *blocks,
                         user=user, active_nav="/admin/integrations",
                         title="AssetHero · Integrations")


def register(app, rt, current_user):

    @rt("/admin/integrations")
    def integrations_get(session, msg: str = ""):
        user = current_user(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        return _page(user, flash=msg)

    @app.post("/admin/integrations/{provider}")
    async def integrations_save(session, request, provider: str):
        user = current_user(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        prov = I.PROVIDERS_BY_KEY.get(provider)
        if not prov:
            return RedirectResponse("/admin/integrations", status_code=303)
        form = await request.form()
        # Merge: keep existing values for blank fields (so "set" secrets persist).
        cfg = I.get_config(user["user_id"], provider)
        for f in prov.fields:
            v = (form.get(f.key) or "").strip()
            if v:
                cfg[f.key] = v
        I.save_config(user["user_id"], provider, cfg, enabled=True)
        return RedirectResponse(f"/admin/integrations?msg=Saved+{prov.name}", status_code=303)

    @app.post("/admin/integrations/{provider}/test")
    async def integrations_test(session, request, provider: str):
        user = current_user(session)
        if not user:
            return RedirectResponse("/login", status_code=303)
        prov = I.PROVIDERS_BY_KEY.get(provider)
        if not prov:
            return RedirectResponse("/admin/integrations", status_code=303)
        # Save any freshly-entered values first, then test.
        form = await request.form()
        cfg = I.get_config(user["user_id"], provider)
        for f in prov.fields:
            v = (form.get(f.key) or "").strip()
            if v:
                cfg[f.key] = v
        if cfg:
            I.save_config(user["user_id"], provider, cfg, enabled=True)
        ok, detail = I.test_connection(user["user_id"], provider)
        verdict = f"{prov.name}: {'OK' if ok else 'failed'} — {detail}"
        return RedirectResponse(f"/admin/integrations?msg={verdict.replace(' ', '+')}", status_code=303)
