#!/usr/bin/env python3
# ══════════════════════════════════════════════════════
#  VLESS+WS Web Panel  —  Python CGI
#  DB       : JSON file
#  Server   : python3 -m http.server --cgi
#  Protocol : VLESS + WebSocket, NO TLS (security: none)
#  Mux      : concurrency 8 (fewer HTTP round-trips)
# ══════════════════════════════════════════════════════
import os
import sys
import json
import uuid
import subprocess
from datetime import datetime, date
from urllib.parse import parse_qs, quote

DB        = "/opt/vless-panel/data/users.json"
CFG       = "/opt/vless-panel/data/config.json"
XRAY_CFG  = "/usr/local/etc/xray/config.json"


# ── Config helpers ─────────────────────────────────────
def cfg_get(key, default=""):
    try:
        with open(CFG) as f:
            c = json.load(f)
        return c.get(key, default)
    except Exception:
        return default


SERVER_IP   = cfg_get("server_ip", "")
VLESS_PORT  = cfg_get("vless_port", 443)
WS_PATH     = cfg_get("ws_path", "/vless")


# ── DB helpers ──────────────────────────────────────────
def load_db():
    try:
        with open(DB) as f:
            return json.load(f)
    except Exception:
        return {"users": []}


def save_db(db):
    with open(DB, "w") as f:
        json.dump(db, f, indent=2)


def add_user(email, expire, limit):
    db = load_db()
    db.setdefault("users", []).append({
        "email":    email,
        "uuid":     str(uuid.uuid4()),
        "created":  datetime.now().strftime("%Y-%m-%d"),
        "expire":   expire or "unlimited",
        "limit_gb": float(limit) if limit else 0,
        "used_gb":  0,
        "enabled":  True,
    })
    save_db(db)


def remove_user(email):
    db = load_db()
    db["users"] = [u for u in db.get("users", []) if u["email"] != email]
    save_db(db)


# ── Rebuild Xray config (non-TLS WS inbound) ───────────
def rebuild_xray():
    db = load_db()
    clients = [
        {"id": u["uuid"], "email": u["email"], "level": 0, "flow": ""}
        for u in db.get("users", []) if u.get("enabled", True)
    ]

    cfg = {
        "log": {
            "loglevel": "warning",
            "access": "/var/log/xray/access.log",
            "error":  "/var/log/xray/error.log",
        },
        "inbounds": [{
            "tag": "vless-ws",
            "port": int(VLESS_PORT),
            "protocol": "vless",
            "settings": {"clients": clients, "decryption": "none"},
            "streamSettings": {
                "network": "ws",
                "security": "none",
                "wsSettings": {"path": WS_PATH},
            },
            "sniffing": {"enabled": True, "destOverride": ["http", "tls"]},
        }],
        "outbounds": [
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block",  "protocol": "blackhole"},
        ],
        "routing": {"rules": [
            {"type": "field", "ip": ["geoip:private"], "outboundTag": "block"},
        ]},
    }
    try:
        with open(XRAY_CFG, "w") as f:
            json.dump(cfg, f, indent=2)
    except OSError:
        return  # xray not installed / dir missing — skip reload

    for cmd in (["systemctl", "reload", "xray"], ["systemctl", "restart", "xray"]):
        try:
            subprocess.run(cmd, check=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            break
        except Exception:
            continue


# ── Client JSON export (non-TLS, Mux + Early Data) ─────
def client_json(email):
    db = load_db()
    users = [u for u in db.get("users", []) if u["email"] == email]
    if not users:
        return None
    u = users[0]

    out = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"tag": "socks", "port": 10808, "protocol": "socks",
             "settings": {"auth": "noauth", "udp": True}},
            {"tag": "http", "port": 10809, "protocol": "http",
             "settings": {}},
        ],
        "outbounds": [
            {
                "tag": "proxy",
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": SERVER_IP,
                        "port": int(VLESS_PORT),
                        "users": [{
                            "id": u["uuid"],
                            "encryption": "none",
                            "level": 0,
                        }],
                    }],
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": {
                        "path": WS_PATH + "?ed=2048",
                        "headers": {"Host": SERVER_IP},
                    },
                },
                "mux": {"enabled": True, "concurrency": 8},
            },
            {"tag": "direct", "protocol": "freedom"},
            {"tag": "block",  "protocol": "blackhole"},
        ],
        "routing": {
            "domainStrategy": "IPIfNonMatch",
            "rules": [{"type": "field", "outboundTag": "direct", "ip": ["geoip:private"]}],
        },
    }
    return json.dumps(out, indent=2, ensure_ascii=False)


# ── HTML / CSS ──────────────────────────────────────────
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0d1117;color:#c9d1d9;min-height:100vh}
.nav{background:#161b22;padding:.9rem 2rem;border-bottom:1px solid #21262d;display:flex;align-items:center;gap:.8rem}
.nav h1{font-size:1.1rem;color:#58a6ff;font-weight:600}
.badge{background:#21262d;color:#3fb950;padding:2px 8px;border-radius:12px;font-size:.72rem;border:1px solid #3fb95040}
.srv{margin-left:auto;font-size:.8rem;color:#6e7681}
.wrap{max-width:1050px;margin:0 auto;padding:1.5rem}
.card{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:1.25rem;margin-bottom:1.25rem}
.card-title{font-size:.85rem;font-weight:600;color:#8b949e;margin-bottom:1rem;text-transform:uppercase;letter-spacing:.05em}
table{width:100%;border-collapse:collapse;font-size:.85rem}
th{text-align:left;padding:.5rem .75rem;color:#6e7681;border-bottom:1px solid #21262d;font-weight:500;font-size:.78rem;text-transform:uppercase}
td{padding:.6rem .75rem;border-bottom:1px solid #161b22;vertical-align:middle}
tr:last-child td{border-bottom:none}
tr:hover td{background:#1c2128}
.tag{display:inline-block;padding:1px 7px;border-radius:12px;font-size:.72rem;font-weight:500}
.ok{background:#1a4a2e;color:#3fb950;border:1px solid #3fb95040}
.exp{background:#4a1a2e;color:#f85149;border:1px solid #f8514940}
.warn{background:#3d2e00;color:#d29922;border:1px solid #d2992240}
.form-row{display:flex;gap:.75rem;flex-wrap:wrap;align-items:flex-end}
.fg{display:flex;flex-direction:column;gap:.35rem}
label{font-size:.72rem;color:#6e7681;font-weight:500}
input[type=text],input[type=date],input[type=number]{
    background:#0d1117;border:1px solid #30363d;color:#c9d1d9;
    padding:.45rem .7rem;border-radius:6px;font-size:.85rem}
input[type=text]{width:160px}
input[type=date]{width:155px}
input[type=number]{width:110px}
input:focus{outline:none;border-color:#58a6ff}
.btn{padding:.4rem .9rem;border:none;border-radius:6px;cursor:pointer;font-size:.8rem;font-weight:500;text-decoration:none;display:inline-block;transition:opacity .15s}
.btn:hover{opacity:.85}
.add{background:#238636;color:#fff}
.del{background:#c53030;color:#fff}
.dl{background:#1f6feb;color:#fff}
.btn-sm{padding:.25rem .6rem;font-size:.75rem}
code{font-size:.75rem;color:#8b949e;font-family:monospace}
.bar-wrap{background:#21262d;border-radius:3px;height:5px;width:80px;display:inline-block;vertical-align:middle;margin-left:4px}
.bar-fill{height:100%;border-radius:3px}
"""


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def user_rows():
    db = load_db()
    users = db.get("users", [])
    if not users:
        return '<tr><td colspan="6" style="text-align:center;color:#6e7681;padding:2rem">No users yet</td></tr>'

    rows = []
    for u in users:
        em    = esc(u.get("email", "?"))
        uid   = esc(u.get("uuid", "?"))
        cre   = esc(u.get("created", "?"))
        exp   = u.get("expire", "unlimited")
        used  = float(u.get("used_gb", 0))
        limit = float(u.get("limit_gb", 0))

        if not exp or exp in ("0", "unlimited", ""):
            exp_h = '<span class="tag ok">∞ No limit</span>'
        else:
            try:
                d = datetime.strptime(exp, "%Y-%m-%d").date()
                diff = (d - date.today()).days
                if diff < 0:
                    exp_h = f'<span class="tag exp">Expired {-diff}d</span>'
                elif diff <= 7:
                    exp_h = f'<span class="tag warn">{diff}d left</span>'
                else:
                    exp_h = f'<span class="tag ok">{esc(exp)}</span>'
            except Exception:
                exp_h = f'<span class="tag ok">{esc(exp)}</span>'

        if limit <= 0:
            tr_h = f'<span style="color:#6e7681">{used:.1f} GB / \u221e</span>'
        else:
            pct = min(used / limit * 100, 100)
            col = "#f85149" if pct > 90 else "#d29922" if pct > 70 else "#3fb950"
            tr_h = (f'{used:.1f}/{limit:.0f}G'
                    f'<span class="bar-wrap"><span class="bar-fill" '
                    f'style="background:{col};width:{pct:.0f}%"></span></span>')

        em_q = quote(em)
        rows.append(f'''
<tr>
  <td><strong>{em}</strong></td>
  <td><code>{uid[:20]}\u2026</code></td>
  <td style="color:#6e7681;font-size:.78rem">{cre}</td>
  <td>{exp_h}</td>
  <td>{tr_h}</td>
  <td>
    <a href="/cgi-bin/panel.cgi?action=export&user={em_q}"
       class="btn dl btn-sm">\u2b07 JSON</a>
    &nbsp;
    <form method="POST" action="/cgi-bin/panel.cgi?action=remove"
          style="display:inline"
          onsubmit="return confirm('Remove {em}?')">
      <input type="hidden" name="email" value="{em}">
      <button class="btn del btn-sm">\u2715</button>
    </form>
  </td>
</tr>''')
    return "".join(rows)


def page_main():
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VLESS Panel</title>
<style>{CSS}</style>
</head>
<body>
<nav class="nav">
  <h1>\u26a1 VLESS Panel</h1>
  <span class="badge">WS \u00b7 no-TLS \u00b7 Mux</span>
  <span class="srv">{esc(SERVER_IP)}:{esc(VLESS_PORT)}{esc(WS_PATH)}</span>
</nav>
<div class="wrap">

<div class="card">
  <div class="card-title">Add User</div>
  <form method="POST" action="/cgi-bin/panel.cgi?action=add">
    <div class="form-row">
      <div class="fg">
        <label>Username</label>
        <input type="text" name="email" placeholder="user1" required>
      </div>
      <div class="fg">
        <label>Expire Date</label>
        <input type="date" name="expire">
      </div>
      <div class="fg">
        <label>Traffic Limit GB (0=\u221e)</label>
        <input type="number" name="limit_gb" value="0" min="0" step="1">
      </div>
      <div class="fg">
        <label>&nbsp;</label>
        <button type="submit" class="btn add">+ Add</button>
      </div>
    </div>
  </form>
</div>

<div class="card">
  <div class="card-title">Users</div>
  <table>
    <thead>
      <tr>
        <th>User</th>
        <th>UUID</th>
        <th>Created</th>
        <th>Expire</th>
        <th>Traffic</th>
        <th>Actions</th>
      </tr>
    </thead>
    <tbody>
{user_rows()}
    </tbody>
  </table>
</div>

</div>
</body>
</html>'''
    sys.stdout.write("Content-Type: text/html; charset=utf-8\r\n\r\n")
    sys.stdout.write(html)


# ── Request plumbing ────────────────────────────────────
def read_post():
    length = int(os.environ.get("CONTENT_LENGTH") or 0)
    if os.environ.get("REQUEST_METHOD") == "POST" and length:
        raw = sys.stdin.buffer.read(length).decode("utf-8", "replace")
        return parse_qs(raw)
    return {}


def qval(d, key, default=""):
    v = d.get(key)
    return v[0] if v else default


def action_add():
    post = read_post()
    email  = qval(post, "email")
    expire = qval(post, "expire")
    limit  = qval(post, "limit_gb")
    if email:
        add_user(email, expire, limit)
        rebuild_xray()
    sys.stdout.write("Content-Type: text/html\r\n\r\n")
    sys.stdout.write('<meta http-equiv="refresh" content="0;url=/cgi-bin/panel.cgi">')


def action_remove():
    post = read_post()
    email = qval(post, "email")
    if email:
        remove_user(email)
        rebuild_xray()
    sys.stdout.write("Content-Type: text/html\r\n\r\n")
    sys.stdout.write('<meta http-equiv="refresh" content="0;url=/cgi-bin/panel.cgi">')


def action_export():
    qs = parse_qs(os.environ.get("QUERY_STRING", ""))
    email = qval(qs, "user")
    payload = client_json(email)
    if payload is None:
        sys.stdout.write("Status: 404 Not Found\r\nContent-Type: text/plain\r\n\r\nUser not found")
        return
    sys.stdout.write("Content-Type: application/json\r\n")
    sys.stdout.write(f'Content-Disposition: attachment; filename="{email}_vless.json"\r\n\r\n')
    sys.stdout.write(payload)


def main():
    method = os.environ.get("REQUEST_METHOD", "GET")
    qs = parse_qs(os.environ.get("QUERY_STRING", ""))
    action = qval(qs, "action")

    if method == "POST" and action == "add":
        action_add()
    elif method == "POST" and action == "remove":
        action_remove()
    elif method == "GET" and action == "export":
        action_export()
    else:
        page_main()

    sys.stdout.flush()


if __name__ == "__main__":
    main()
