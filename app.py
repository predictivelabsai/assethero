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
    A, Div, Form, H2, P, serve, fast_app, NotStr,
)
from starlette.responses import RedirectResponse  # noqa: E402

from engine.auth import (  # noqa: E402
    authenticate, create_user, get_user_by_id, get_user_by_email, get_user_accounts,
    get_user_by_google_id, link_google_id,
)
from engine.web.layout import page  # noqa: E402
from engine.web import landing  # noqa: E402
import verticals.equities.routes as equities  # noqa: E402

app, rt = fast_app(
    pico=False,
    # Stable session secret so cookies survive restarts / multiple instances
    # (without this, FastHTML regenerates a key per process and logs everyone out).
    secret_key=os.getenv("SESSION_SECRET", "assethero-dev-secret-change-me"),
    static_path="static",
)

# --------------------------------------------------------------- Google OAuth
# Optional — gracefully disabled unless GOOGLE_CLIENT_ID/SECRET are set.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
_oauth_enabled = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
_authlib_oauth = None
if _oauth_enabled:
    from authlib.integrations.starlette_client import OAuth as AuthlibOAuth  # noqa: E402
    _authlib_oauth = AuthlibOAuth()
    _authlib_oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


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
    parts = [H2("Sign in", cls="text-xl font-bold text-center mb-4",
                style=f"color:{landing.INK};")]
    parts.append(landing.auth_error(error))
    if _oauth_enabled:
        parts.append(landing.google_btn("Continue with Google"))
        parts.append(landing._auth_divider())
    parts.append(Form(
        landing.auth_input("email", "Email", itype="email", value=email, required=True, autofocus=True),
        landing.auth_input("password", "Password", itype="password", required=True),
        landing.auth_submit("Sign in"),
        method="post", action="/login", cls="flex flex-col gap-3",
    ))
    parts.append(Div("Don't have an account? ",
                     A("Create one", href="/register", style=f"color:{landing.CTA};"),
                     cls="text-center text-sm mt-4", style=f"color:{landing.INK_MUTED};"))
    return landing.auth_page(*parts, title="Sign in")


def _register_form(error=None, email=""):
    parts = [H2("Create account", cls="text-xl font-bold text-center mb-4",
                style=f"color:{landing.INK};")]
    parts.append(landing.auth_error(error))
    if _oauth_enabled:
        parts.append(landing.google_btn("Sign up with Google"))
        parts.append(landing._auth_divider())
    parts.append(Form(
        landing.auth_input("display_name", "Display name (optional)"),
        landing.auth_input("email", "Email", itype="email", value=email, required=True),
        landing.auth_input("password", "Password", itype="password", required=True, minlength="8"),
        landing.auth_submit("Create account"),
        method="post", action="/register", cls="flex flex-col gap-3",
    ))
    parts.append(Div("Already have an account? ",
                     A("Sign in", href="/login", style=f"color:{landing.CTA};"),
                     cls="text-center text-sm mt-4", style=f"color:{landing.INK_MUTED};"))
    return landing.auth_page(*parts, title="Create account")


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


# ------------------------------------------------------------ Google OAuth
@rt("/auth/google")
async def auth_google(request):
    if not _oauth_enabled:
        return RedirectResponse("/login", status_code=303)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    redirect_uri = f"{scheme}://{host}/auth/callback"
    return await _authlib_oauth.google.authorize_redirect(request, redirect_uri)


@rt("/auth/callback")
async def auth_callback(request, session):
    if not _oauth_enabled:
        return RedirectResponse("/login", status_code=303)
    try:
        token = await _authlib_oauth.google.authorize_access_token(request)
    except Exception:  # noqa: BLE001
        return RedirectResponse("/login", status_code=303)
    userinfo = token.get("userinfo") or {}
    if not userinfo:
        try:
            userinfo = await _authlib_oauth.google.userinfo(token=token)
        except Exception:  # noqa: BLE001
            userinfo = {}
    google_id = userinfo.get("sub", "")
    email = userinfo.get("email", "")
    name = userinfo.get("name", "")
    if not email:
        return RedirectResponse("/login", status_code=303)
    try:
        user = get_user_by_google_id(google_id) if google_id else None
        if not user:
            user = get_user_by_email(email)
            if user and google_id:
                link_google_id(email, google_id)
            elif not user:
                user = create_user(email=email, google_id=google_id, display_name=name)
    except Exception:  # noqa: BLE001
        return RedirectResponse("/login", status_code=303)
    if not user:
        return RedirectResponse("/login", status_code=303)
    session["user_id"] = user["user_id"]
    return RedirectResponse("/equities", status_code=303)


# ------------------------------------------------------------ landing pages
@rt("/")
def root():
    return landing.home_page()


@rt("/asset-classes")
def asset_classes():
    return landing.asset_classes_page()


@rt("/how-it-works")
def how_it_works():
    return landing.how_it_works_page()


@rt("/pricing")
def pricing():
    return landing.pricing_page()


@rt("/contact")
def contact():
    return landing.contact_page()


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


# ---------------------------------------------------------- admin / integrations
from engine.web import admin as _admin  # noqa: E402
from engine.web import layout as _layout  # noqa: E402
from engine.web import commands as _commands  # noqa: E402
_admin.register(app, rt, current_user)


# --------------------------------------------------------------- verticals
equities.register(app, rt, current_user)


def _register_vertical(key, module_path):
    """Import + register a vertical, enable its switcher pill and shortcuts.
    Resilient: a broken vertical degrades to a 'soon' stub instead of crashing boot."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        mod.register(app, rt, current_user)
        _layout.enable_vertical(key)
        _commands.register_shortcuts(key, getattr(mod, "SHORTCUTS", None))
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).warning("vertical %s unavailable: %s", key, e)


for _v, _mod in [("crypto", "verticals.crypto.routes"),
                 ("prediction", "verticals.prediction.routes"),
                 ("fx", "verticals.fx.routes")]:
    _register_vertical(_v, _mod)

# Research stays a stub until its merge phase.
rt("/research")(_make_stub("research", "Research"))


if __name__ == "__main__":
    port = int(os.getenv("PORT") or os.getenv("ASSETHERO_WEB_PORT") or "5001")
    _prod = os.getenv("ENVIRONMENT", "").lower() == "production"
    serve(host="0.0.0.0", port=port, reload=not _prod)
