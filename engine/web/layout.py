"""House-style chat-first shell + design tokens for the assethero platform UI.

`page(...)` wraps every vertical view in: a top bar (brand · asset-class switcher ·
user menu) and a 3-pane body:

  left   — "+ New chat", chat history, vertical nav, and the shared main-nav menu
  center — the chat (messages · welcome · input · agent shortcuts below the box)
  right  — the vertical "workspace" (dashboards, tables, results the vertical passes in)

Chat posts to `/{vertical}/assistant` and keeps history client-side (localStorage),
so the shell works without a database. Dark-navy + amber house style, shared with
the marketing landing (engine/web/landing.py) and the same hex tokens.
"""
from __future__ import annotations

from typing import Optional

from fasthtml.common import (
    A, Button, Div, Form, H1, H3, Input, Li, Link, Main, Meta, Nav, P, Script,
    Span, Style, Textarea, Title, Ul, NotStr,
)

# --- asset-class registry (drives the top-bar switcher) ---------------------
# (key, label, icon, href, enabled)
ASSET_CLASSES = [
    ("equities", "Equities", "📈", "/equities", True),
    ("crypto", "Crypto", "🪙", "/crypto", False),
    ("fx", "FX / Macro", "💱", "/fx", False),
    ("prediction", "Prediction", "🔮", "/prediction", False),
    ("research", "Research", "🔬", "/research", False),
]

# Shared <head> bits: UTF-8 charset (so emoji render), viewport, Google Fonts.
HEAD_META = (
    Meta(charset="utf-8"),
    Meta(name="viewport", content="width=device-width, initial-scale=1"),
    Link(rel="preconnect", href="https://fonts.googleapis.com"),
    Link(rel="preconnect", href="https://fonts.gstatic.com", crossorigin=""),
    Link(href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap",
         rel="stylesheet"),
)

LAYOUT_CSS = """
:root{
  --bg:#0B1220; --panel:#111A2E; --panel-2:#0f1830; --line:#1E293B;
  --text:#E5E7EB; --muted:#94A3B8; --accent:#F59E0B; --accent-2:#10B981;
  --info:#3B82F6; --warn:#F59E0B; --danger:#EF4444; --radius:12px;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);
  font-family:'Inter',system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  font-size:14px;letter-spacing:-0.01em;}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
h1,h2,h3,h4{margin:.2rem 0 .6rem}
.topbar{display:flex;align-items:center;gap:1rem;padding:.55rem 1rem;background:var(--panel);
  border-bottom:1px solid var(--line);position:sticky;top:0;z-index:20;height:49px}
.brand{font-weight:800;font-size:1.1rem;letter-spacing:.3px;color:var(--text);white-space:nowrap}
.brand .h{color:var(--accent)}
.switcher{display:flex;gap:.35rem;flex-wrap:wrap;flex:1}
.pill{display:inline-flex;align-items:center;gap:.35rem;padding:.32rem .7rem;border-radius:999px;
  background:var(--panel-2);border:1px solid var(--line);color:var(--muted);font-weight:600;font-size:.82rem}
.pill.active{background:var(--accent);border-color:var(--accent);color:#111}
.pill.disabled{opacity:.5;cursor:not-allowed}
.pill .soon{font-size:.62rem;opacity:.8}
.usermenu{display:flex;align-items:center;gap:.6rem;color:var(--muted);white-space:nowrap}

.appgrid{display:grid;grid-template-columns:230px 1fr 360px;height:calc(100vh - 49px)}

/* ---- left pane ---- */
.leftpane{background:var(--panel);border-right:1px solid var(--line);padding:.7rem .6rem;
  overflow-y:auto;display:flex;flex-direction:column;gap:.2rem}
.newchat{display:flex;align-items:center;justify-content:center;gap:.4rem;width:100%;
  background:transparent;border:1px solid var(--accent);color:var(--accent);font-weight:700;
  border-radius:10px;padding:.55rem .7rem;cursor:pointer;font-size:.85rem}
.newchat:hover{background:rgba(245,158,11,.1)}
.navhead{font-size:.66rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
  font-weight:700;margin:.9rem .4rem .3rem;opacity:.8}
.history{display:flex;flex-direction:column;gap:.1rem}
.histitem{display:flex;align-items:center;gap:.45rem;text-align:left;background:transparent;border:none;
  color:var(--muted);font-size:.8rem;padding:.4rem .5rem;border-radius:7px;cursor:pointer;width:100%;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.histitem:hover{background:var(--panel-2);color:var(--text)}
.histitem.active{background:var(--panel-2);color:var(--text)}
.histitem .dot{width:6px;height:6px;border-radius:999px;background:var(--line);flex:none}
.histitem.active .dot{background:var(--accent)}
.histempty{color:var(--muted);font-size:.76rem;padding:.3rem .5rem;opacity:.7}
.leftnav ul{list-style:none;margin:.2rem 0;padding:0}
.leftnav li{margin:.12rem 0}
.leftnav a{display:block;padding:.42rem .6rem;border-radius:8px;color:var(--muted);font-weight:600;font-size:.85rem}
.leftnav a:hover{background:var(--panel-2);text-decoration:none;color:var(--text)}
.leftnav a.active{background:var(--panel-2);color:var(--text);border-left:3px solid var(--accent)}

/* collapsible command groups (left main-nav + shortcut groups) */
.cgroup{margin-bottom:.04rem}
.ctoggle{display:flex;align-items:center;width:100%;gap:.4rem;background:transparent;border:none;
  color:var(--muted);font-weight:700;font-size:.75rem;padding:.4rem .55rem;cursor:pointer;border-radius:8px}
.ctoggle:hover{background:var(--panel-2);color:var(--text)}
.ccount{font-size:.6rem;background:var(--panel-2);border:1px solid var(--line);border-radius:999px;
  padding:.02rem .42rem;color:var(--muted)}
.carrow{margin-left:auto;transition:transform .15s ease;font-size:.7rem}
.cgroup.open .carrow{transform:rotate(90deg)}
.clist{display:none;flex-direction:column;gap:.08rem;padding:.05rem .3rem .3rem}
.cgroup.open .clist{display:flex}
.citem{text-align:left;background:transparent;border:none;color:var(--muted);font-size:.72rem;
  padding:.3rem .5rem;border-radius:6px;cursor:pointer;
  font-family:'JetBrains Mono',ui-monospace,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.citem:hover{background:var(--panel-2);color:var(--accent)}

/* ---- center chat pane ---- */
.chatpane{display:flex;flex-direction:column;min-width:0;height:100%;background:var(--bg)}
.chathead{display:flex;align-items:center;gap:.5rem;padding:.6rem 1rem;border-bottom:1px solid var(--line);
  color:var(--muted);font-size:.85rem}
.chathead .title{color:var(--text);font-weight:700}
.messages{flex:1;overflow-y:auto;padding:1rem 1.1rem;display:flex;flex-direction:column;gap:.8rem}
.welcome{margin:auto;text-align:center;max-width:520px;padding:2rem 1rem}
.welcome .mark{font-size:2rem;color:var(--accent)}
.welcome h1{font-size:1.5rem;font-weight:800;letter-spacing:-.03em;margin:.4rem 0}
.welcome p{color:var(--muted);font-size:.9rem}
.msg{display:flex;flex-direction:column;max-width:88%}
.msg.user{align-self:flex-end;align-items:flex-end}
.msg.assistant{align-self:flex-start}
.msg .who{font-size:.66rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 .3rem .2rem}
.bubble{padding:.6rem .8rem;border-radius:12px;line-height:1.5;font-size:.88rem;overflow-x:auto}
.msg.user .bubble{background:var(--accent);color:#111;border-top-right-radius:4px;font-weight:500}
.msg.assistant .bubble{background:var(--panel);border:1px solid var(--line);color:var(--text);border-top-left-radius:4px}
.bubble code{background:var(--panel-2);border:1px solid var(--line);border-radius:5px;padding:.05rem .3rem;
  font-family:'JetBrains Mono',ui-monospace,monospace;font-size:.82em}
.bubble.thinking{color:var(--muted);font-style:italic}

.composer{border-top:1px solid var(--line);padding:.7rem .9rem .9rem;background:var(--bg)}
.chatform{display:flex;gap:.5rem;align-items:flex-end}
.chatform textarea{flex:1;resize:none;background:var(--panel);border:1px solid var(--line);color:var(--text);
  border-radius:10px;padding:.6rem .7rem;font:inherit;font-size:.9rem;max-height:160px;min-height:44px}
.chatform textarea:focus{outline:none;border-color:var(--accent)}
.chatsend{background:var(--accent);color:#111;border:none;border-radius:10px;padding:.6rem 1.1rem;
  font-weight:700;cursor:pointer;height:44px}
.chatsend:hover{filter:brightness(1.08)}
.shortcuts{margin-top:.55rem}
.shortcuts .shhead{font-size:.66rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
  font-weight:700;margin:.1rem .1rem .3rem}
.shrow{display:flex;flex-wrap:wrap;gap:.3rem}
.shgroup{position:relative}
.shpill{background:var(--panel);border:1px solid var(--line);color:var(--muted);border-radius:999px;
  padding:.28rem .6rem;font-size:.73rem;cursor:pointer;font-weight:600}
.shpill:hover{border-color:var(--accent);color:var(--accent)}
.shpill .n{font-size:.6rem;opacity:.8;margin-left:.25rem}
.shmenu{display:none;position:absolute;bottom:110%;left:0;z-index:30;min-width:230px;
  background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:.3rem;flex-direction:column;gap:.05rem;
  box-shadow:0 10px 30px rgba(0,0,0,.4)}
.shgroup.open .shmenu{display:flex}
.shmenu button{text-align:left;background:transparent;border:none;color:var(--muted);font-size:.74rem;
  padding:.32rem .5rem;border-radius:6px;cursor:pointer;font-family:'JetBrains Mono',ui-monospace,monospace}
.shmenu button:hover{background:var(--panel-2);color:var(--accent)}

/* ---- right workspace pane ---- */
.workspace{background:var(--panel);border-left:1px solid var(--line);padding:.9rem .9rem;overflow-y:auto}
.workspace .wshead{font-size:.66rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
  font-weight:700;margin-bottom:.6rem;opacity:.85}
.card{background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius);padding:1rem;margin-bottom:1rem}
.kpi{display:flex;gap:.6rem;flex-wrap:wrap}
.kpi .box{flex:1;min-width:100px;background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius);padding:.7rem .8rem}
.kpi .box .v{font-size:1.15rem;font-weight:800}
.kpi .box .l{color:var(--muted);font-size:.72rem;text-transform:uppercase;letter-spacing:.04em}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th,td{text-align:left;padding:.45rem .5rem;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-weight:700;text-transform:uppercase;font-size:.68rem;letter-spacing:.04em}
.pos{color:var(--accent-2)} .neg{color:var(--danger)}
input,select,button{font:inherit}
input,select{background:var(--bg);border:1px solid var(--line);color:var(--text);border-radius:8px;padding:.5rem .6rem}
.btn{background:var(--accent);color:#111;border:none;border-radius:8px;padding:.55rem .9rem;font-weight:700;cursor:pointer}
.btn:hover{filter:brightness(1.08)}
.btn.ghost{background:var(--panel-2);color:var(--text);border:1px solid var(--line)}
.muted{color:var(--muted)} .right{text-align:right}
.authwrap{max-width:380px;margin:8vh auto;padding:0 1rem}
.formrow{display:flex;flex-direction:column;gap:.3rem;margin-bottom:.8rem}
.notice{padding:.6rem .8rem;border-radius:8px;background:var(--panel-2);border:1px solid var(--line);margin-bottom:1rem}
.err{border-color:var(--danger);color:#ffd7d7}

.appgrid.two{grid-template-columns:230px 1fr}
.settings{padding:1.4rem 1.6rem;overflow-y:auto}
.settings h2{font-size:1.4rem;font-weight:800;letter-spacing:-.03em;margin-bottom:.2rem}
.settings .sub{color:var(--muted);margin-bottom:1.4rem}
.settings .navhead2{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
  font-weight:700;margin:1.4rem 0 .7rem}
.intgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:1rem}
.intcard{background:var(--panel-2);border:1px solid var(--line);border-radius:12px;padding:1rem}
.intcard .hd{display:flex;align-items:center;gap:.5rem;margin-bottom:.2rem}
.intcard .hd .nm{font-weight:700}
.intcard .hd .st{margin-left:auto;font-size:.66rem;text-transform:uppercase;letter-spacing:.04em;
  padding:.1rem .45rem;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.intcard .hd .st.ok{color:#111;background:var(--accent-2);border-color:var(--accent-2)}
.intcard .hd .st.error{color:#fff;background:var(--danger);border-color:var(--danger)}
.intcard .hd .st.set{color:var(--accent);border-color:var(--accent)}
.intcard .help{color:var(--muted);font-size:.8rem;margin-bottom:.7rem}
.intcard label{display:block;font-size:.72rem;color:var(--muted);margin:.5rem 0 .2rem}
.intcard input{width:100%}
.intcard .acts{display:flex;gap:.5rem;margin-top:.8rem}
.flash{padding:.5rem .8rem;border-radius:8px;background:var(--panel-2);border:1px solid var(--accent-2);
  color:var(--accent-2);margin-bottom:1rem;font-size:.85rem}

@media (max-width:1100px){.appgrid{grid-template-columns:200px 1fr}.workspace{display:none}}
@media (max-width:760px){.appgrid{grid-template-columns:1fr}.leftpane{display:none}}
"""

CHAT_JS = """
function ahVertical(){var r=document.getElementById('ah-root');return r?r.getAttribute('data-vertical'):'equities';}
function ahKey(){return 'ah_threads_'+ahVertical();}
function ahCurKey(){return 'ah_cur_'+ahVertical();}
function ahLoad(){try{return JSON.parse(localStorage.getItem(ahKey())||'[]');}catch(e){return [];}}
function ahSave(t){localStorage.setItem(ahKey(),JSON.stringify(t));}
function ahCur(){return localStorage.getItem(ahCurKey())||'';}
function ahSetCur(id){localStorage.setItem(ahCurKey(),id);}
function ahThread(id){return ahLoad().find(function(t){return t.id===id;});}

function ahEsc(s){var d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function ahBubble(role,html,thinking){
  var wrap=document.createElement('div');wrap.className='msg '+role;
  var who=document.createElement('div');who.className='who';who.textContent=(role==='user'?'You':'Assistant');
  var b=document.createElement('div');b.className='bubble'+(thinking?' thinking':'');b.innerHTML=html;
  wrap.appendChild(who);wrap.appendChild(b);return wrap;
}
function ahRender(){
  var box=document.getElementById('messages');if(!box)return;
  var t=ahThread(ahCur());
  box.innerHTML='';
  if(!t||!t.messages.length){box.appendChild(ahWelcome());return;}
  t.messages.forEach(function(m){box.appendChild(ahBubble(m.role, m.role==='user'?ahEsc(m.content):m.content));});
  box.scrollTop=box.scrollHeight;
}
function ahWelcome(){
  var d=document.createElement('div');d.className='welcome';
  d.innerHTML='<div class="mark">◆</div><h1>How can I help?</h1>'+
    '<p>Ask about your data or run a command. Try a shortcut below, e.g. '+
    '<code>runs</code>, <code>trades</code>, or <code>agent:backtest lookback:1m</code>.</p>';
  return d;
}
function ahHistory(){
  var host=document.getElementById('ah-history');if(!host)return;
  var t=ahLoad();host.innerHTML='';
  if(!t.length){var e=document.createElement('div');e.className='histempty';e.textContent='No chats yet.';host.appendChild(e);return;}
  t.slice().reverse().forEach(function(th){
    var b=document.createElement('button');b.className='histitem'+(th.id===ahCur()?' active':'');b.type='button';
    b.onclick=function(){ahSetCur(th.id);ahRender();ahHistory();};
    var dot=document.createElement('span');dot.className='dot';
    var lbl=document.createElement('span');lbl.textContent=th.title||'New chat';
    b.appendChild(dot);b.appendChild(lbl);host.appendChild(b);
  });
}
function ahNewId(){return 'c'+Date.now()+Math.floor(Math.random()*1000);}
function newChat(){var id=ahNewId();var t=ahLoad();t.push({id:id,title:'',messages:[],ts:Date.now()});ahSave(t);ahSetCur(id);ahRender();ahHistory();
  var i=document.getElementById('ah-ask');if(i)i.focus();}
function ahEnsure(){if(!ahCur()||!ahThread(ahCur())){newChat();}}

function ahToggle(btn){var g=btn.closest('.cgroup'); if(g) g.classList.toggle('open');}
function fillChat(t){var i=document.getElementById('ah-ask');if(i){i.value=t;i.focus();ahAutoResize(i);}}
function ahAutoResize(el){el.style.height='auto';el.style.height=Math.min(el.scrollHeight,160)+'px';}
function ahToggleGroup(btn){var g=btn.closest('.shgroup');document.querySelectorAll('.shgroup.open').forEach(function(o){if(o!==g)o.classList.remove('open');});if(g)g.classList.toggle('open');}
document.addEventListener('click',function(e){if(!e.target.closest('.shgroup'))document.querySelectorAll('.shgroup.open').forEach(function(o){o.classList.remove('open');});});

function ahSend(){
  var i=document.getElementById('ah-ask');if(!i)return;var q=i.value.trim();if(!q)return;
  ahEnsure();var cur=ahCur();var t=ahLoad();var th=t.find(function(x){return x.id===cur;});
  th.messages.push({role:'user',content:q});if(!th.title)th.title=q.slice(0,42);ahSave(t);
  i.value='';ahAutoResize(i);ahRender();ahHistory();
  var box=document.getElementById('messages');var pend=ahBubble('assistant','…thinking',true);box.appendChild(pend);box.scrollTop=box.scrollHeight;
  fetch('/'+ahVertical()+'/assistant',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:'q='+encodeURIComponent(q)})
   .then(function(r){return r.text();})
   .then(function(html){
     var t2=ahLoad();var th2=t2.find(function(x){return x.id===cur;});if(th2){th2.messages.push({role:'assistant',content:html});ahSave(t2);}
     ahRender();
   })
   .catch(function(err){var t2=ahLoad();var th2=t2.find(function(x){return x.id===cur;});if(th2){th2.messages.push({role:'assistant',content:'<span class="neg">error: '+ahEsc(String(err))+'</span>'});ahSave(t2);}ahRender();});
}
function ahKeydown(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ahSend();}}
document.addEventListener('DOMContentLoaded',function(){ahEnsure();ahRender();ahHistory();});
"""


# Verticals whose routes registered successfully (drives which pills are live).
ENABLED_VERTICALS = {k for k, _l, _i, _h, en in ASSET_CLASSES if en}


def enable_vertical(key: str) -> None:
    ENABLED_VERTICALS.add(key)


def switcher(active: str):
    pills = []
    for key, label, icon, href, _static_enabled in ASSET_CLASSES:
        enabled = key in ENABLED_VERTICALS
        cls = "pill" + (" active" if key == active else "") + ("" if enabled else " disabled")
        inner = [Span(icon), Span(label)]
        if not enabled:
            inner.append(Span("soon", cls="soon"))
        pills.append(A(*inner, cls=cls, href=(href if enabled else "#"),
                       title=("" if enabled else "Coming in a later phase")))
    return Div(*pills, cls="switcher")


def topbar(active: str, user: Optional[dict]):
    if user:
        right = Div(Span(user.get("email", "user"), cls="muted"),
                    A("Profile", href="/profile"), A("Logout", href="/logout"), cls="usermenu")
    else:
        right = Div(A("Login", href="/login"), cls="usermenu")
    return Div(
        A(Div(NotStr('Asset<span class="h">Hero</span>'), cls="brand"), href="/"),
        switcher(active),
        right,
        cls="topbar",
    )


def command_groups(groups):
    """Collapsible (name · count · commands) groups for the left main-nav."""
    out = []
    for name, items in groups:
        toggle = Button(Span(name), Span(str(len(items)), cls="ccount"), Span("›", cls="carrow"),
                        cls="ctoggle", type="button", onclick="ahToggle(this)")
        lst = Div(*[Button(cmd, cls="citem", type="button", title=desc,
                           onclick=f"fillChat({cmd!r})") for cmd, desc in items], cls="clist")
        out.append(Div(toggle, lst, cls="cgroup"))
    return Div(*out)


def left_pane(active_vertical: str, nav_items, active_nav: str):
    from engine.web.commands import MAIN_NAV
    items = [Li(A(label, href=href, cls=("active" if href == active_nav else None)))
             for label, href in nav_items]
    admin = Nav(Ul(
        Li(A("🔌 Integrations", href="/admin/integrations",
             cls=("active" if active_nav == "/admin/integrations" else None))),
        Li(A("👤 Profile", href="/profile", cls=("active" if active_nav == "/profile" else None))),
    ), cls="leftnav")
    return Div(
        Button("＋ New chat", cls="newchat", type="button", onclick="newChat()"),
        Div("History", cls="navhead"),
        Div(cls="history", id="ah-history"),
        Div("Views", cls="navhead"),
        Nav(Ul(*items), cls="leftnav"),
        Div("Menu", cls="navhead"),
        command_groups(MAIN_NAV),
        Div("Admin", cls="navhead"),
        admin,
        cls="leftpane",
    )


def _shortcut_bar(active_vertical: str = "equities"):
    """Agent-shortcut pills shown below the chat input; each opens its command list.
    Shows the active vertical's shortcuts (falls back to equities)."""
    from engine.web.commands import shortcuts_for
    pills = []
    for name, items in shortcuts_for(active_vertical):
        menu = Div(*[Button(cmd, type="button", title=desc, onclick=f"fillChat({cmd!r})")
                     for cmd, desc in items], cls="shmenu")
        pills.append(Div(
            Button(Span(name), Span(str(len(items)), cls="n"), cls="shpill", type="button",
                   onclick="ahToggleGroup(this)"),
            menu, cls="shgroup",
        ))
    return Div(
        Div("Agent shortcuts", cls="shhead"),
        Div(*pills, cls="shrow"),
        cls="shortcuts",
    )


def chat_pane(active_vertical: str, chat_title: str = "AI Assistant"):
    return Div(
        Div(Span("🤖", ), Span(chat_title, cls="title"),
            Span("·", ), Span("keyless quick-answer", cls="muted"), cls="chathead"),
        Div(cls="messages", id="messages"),
        Div(
            Form(
                Textarea(id="ah-ask", name="q", rows="2", placeholder="Ask anything — or type a command like  runs · trades · agent:backtest lookback:1m",
                         onkeydown="ahKeydown(event)", oninput="ahAutoResize(this)"),
                Button("Send", type="button", cls="chatsend", onclick="ahSend()"),
                cls="chatform", onsubmit="return false;",
            ),
            _shortcut_bar(active_vertical),
            cls="composer",
        ),
        cls="chatpane",
    )


def workspace_pane(*content, title: str = "Workspace"):
    return Div(Div(title, cls="wshead"), *content, cls="workspace")


def page(active_vertical: str, nav_items, *content, user: Optional[dict] = None,
         active_nav: str = "", title: str = "AssetHero", right_rail=None,
         rail_chips=None):
    """Chat-first 3-pane page. Vertical `*content` renders in the right workspace pane."""
    workspace = right_rail if right_rail is not None else workspace_pane(*content)
    return (
        Title(title),
        *HEAD_META,
        Style(LAYOUT_CSS),
        Script(CHAT_JS),
        Div(
            topbar(active_vertical, user),
            Div(
                left_pane(active_vertical, nav_items, active_nav),
                chat_pane(active_vertical),
                workspace,
                cls="appgrid",
            ),
            id="ah-root", data_vertical=active_vertical,
        ),
    )


def settings_page(active_vertical: str, nav_items, *content, user: Optional[dict] = None,
                  active_nav: str = "", title: str = "AssetHero"):
    """Full-width settings shell: topbar + left nav + wide content (no chat/workspace)."""
    return (
        Title(title),
        *HEAD_META,
        Style(LAYOUT_CSS),
        Script(CHAT_JS),
        Div(
            topbar(active_vertical, user),
            Div(
                left_pane(active_vertical, nav_items, active_nav),
                Main(*content, cls="settings"),
                cls="appgrid two",
            ),
            id="ah-root", data_vertical=active_vertical,
        ),
    )


def auth_page(*content, title="AssetHero"):
    """Minimal centered shell for login/register (kept for compatibility)."""
    return (
        Title(title),
        *HEAD_META,
        Style(LAYOUT_CSS),
        Div(Div(NotStr('Asset<span class="h">Hero</span>'), cls="brand",
                style="font-size:1.6rem;text-align:center;margin-bottom:1.2rem"),
            *content, cls="authwrap"),
    )
