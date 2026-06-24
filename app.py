"""assethero unified web app (Phase 1) — port 5001.

One FastHTML entry point: the shared house-style 3-pane shell + asset-class switcher,
root authentication, and the equities vertical mounted under /equities/*. The other
verticals (crypto, fx, prediction, research) are stubs until their merge phases.

Run:  ASSETHERO_WEB_PORT=5001 python app.py
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

from fasthtml.common import (  # noqa: E402
    A, Button, Div, Form, H2, Input, Label, P, serve, fast_app, NotStr,
)
from starlette.responses import RedirectResponse  # noqa: E402

from engine.auth import (  # noqa: E402
    authenticate, create_user, get_user_by_id, get_user_by_email, get_user_accounts,
)
from engine.web.layout import auth_page, page  # noqa: E402
import verticals.equities.routes as equities  # noqa: E402

app, rt = fast_app(pico=False)


def current_user(session):
    uid = session.get("user_id")
    if not uid:
        return None
    try:
        return get_user_by_id(uid)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- auth
def _login_form(error=None, email=""):
    rows = [
        Div(Label("Email"), Input(name="email", type="email", value=email), cls="formrow"),
        Div(Label("Password"), Input(name="password", type="password"), cls="formrow"),
        Button("Log in", cls="btn", type="submit", style="width:100%"),
    ]
    blocks = []
    if error:
        blocks.append(Div(error, cls="notice err"))
    blocks.append(Form(*rows, method="post", action="/login"))
    blocks.append(P(A("Create an account", href="/register"), cls="muted",
                    style="text-align:center;margin-top:1rem"))
    return auth_page(*blocks, title="AssetHero · Login")


def _register_form(error=None, email=""):
    rows = [
        Div(Label("Display name"), Input(name="display_name"), cls="formrow"),
        Div(Label("Email"), Input(name="email", type="email", value=email), cls="formrow"),
        Div(Label("Password"), Input(name="password", type="password"), cls="formrow"),
        Button("Create account", cls="btn", type="submit", style="width:100%"),
    ]
    blocks = []
    if error:
        blocks.append(Div(error, cls="notice err"))
    blocks.append(Form(*rows, method="post", action="/register"))
    blocks.append(P(A("Back to login", href="/login"), cls="muted",
                    style="text-align:center;margin-top:1rem"))
    return auth_page(*blocks, title="AssetHero · Register")


@rt("/login", methods=["GET"])
def login_get(session):
    if current_user(session):
        return RedirectResponse("/equities", status_code=303)
    return _login_form()


@app.post("/login")
async def login_post(session, request):
    form = await request.form()
    email = (form.get("email") or "").strip()
    pw = form.get("password") or ""
    try:
        user = authenticate(email, pw)
    except Exception:  # noqa: BLE001
        user = None
    if not user:
        return _login_form(error="Invalid email or password.", email=email)
    session["user_id"] = user["user_id"]
    return RedirectResponse("/equities", status_code=303)


@rt("/register", methods=["GET"])
def register_get(session):
    if current_user(session):
        return RedirectResponse("/equities", status_code=303)
    return _register_form()


@app.post("/register")
async def register_post(session, request):
    form = await request.form()
    email = (form.get("email") or "").strip()
    pw = form.get("password") or ""
    dn = (form.get("display_name") or "").strip() or None
    if not email or not pw:
        return _register_form(error="Email and password are required.", email=email)
    try:
        if get_user_by_email(email):
            return _register_form(error="That email is already registered.", email=email)
        user = create_user(email=email, password=pw, display_name=dn)
    except Exception as e:  # noqa: BLE001
        return _register_form(error=f"Could not create account: {e}", email=email)
    session["user_id"] = user["user_id"]
    return RedirectResponse("/equities", status_code=303)


@rt("/logout")
def logout(session):
    session.pop("user_id", None)
    return RedirectResponse("/login", status_code=303)


@rt("/")
def root(session):
    return RedirectResponse("/equities" if current_user(session) else "/login", status_code=303)


@rt("/profile")
def profile(session):
    user = current_user(session)
    if not user:
        return RedirectResponse("/login", status_code=303)
    try:
        accounts = get_user_accounts(user["user_id"])
    except Exception:  # noqa: BLE001
        accounts = []
    nav = [("Dashboard", "/equities"), ("Profile", "/profile")]
    body = [
        H2("Profile"),
        Div(
            P(NotStr(f"<b>Email:</b> {user.get('email', '')}")),
            P(NotStr(f"<b>Name:</b> {user.get('display_name') or '—'}")),
            P(NotStr(f"<b>Linked Alpaca accounts:</b> {len(accounts)}")),
            cls="card",
        ),
    ]
    return page("equities", nav, *body, user=user, active_nav="/profile",
                title="AssetHero · Profile")


# ----------------------------------------------------------------- vertical stubs
def _stub(vertical, label, session):
    user = current_user(session)
    if not user:
        return RedirectResponse("/login", status_code=303)
    body = [
        H2(label),
        Div(P(f"The {label} vertical is coming in a later phase of the assethero merge."),
            P("Equities is live now — use the switcher above.", cls="muted"),
            cls="card"),
    ]
    return page(vertical, [("Overview", f"/{vertical}")], *body, user=user,
                title=f"AssetHero · {label}")


def _make_stub(vertical, label):
    def handler(session):
        return _stub(vertical, label, session)
    return handler


for _v, _l in [("crypto", "Crypto"), ("fx", "FX / Macro"),
               ("prediction", "Prediction"), ("research", "Research")]:
    rt(f"/{_v}")(_make_stub(_v, _l))


# --------------------------------------------------------------- equities vertical
equities.register(app, rt, current_user)


if __name__ == "__main__":
    serve(port=int(os.getenv("ASSETHERO_WEB_PORT", "5001")))
