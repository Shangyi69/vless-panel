#!/usr/init/env python3
import http.server, socketserver, json, uuid, os, subprocess
from urllib.parse import parse_qs, urlparse

PORT = 1190
BASE_DIR = "/opt/vless-panel"
DB_FILE = os.path.join(BASE_DIR, "data/users.json")
CFG_FILE = os.path.join(BASE_DIR, "data/config.json")
XRAY_CFG = "/usr/local/etc/xray/config.json"

class VlessHandler(http.server.SimpleHTTPRequestHandler):
    def load_db(self):
        if not os.path.exists(DB_FILE): return {"users": []}
        with open(DB_FILE, 'r') as f: return json.load(f)

    def save_db(self, db):
        with open(DB_FILE, 'w') as f: json.dump(db, f, indent=4)

    def load_cfg(self):
        default_cfg = {"server_ip": "127.0.0.1", "vless_port": 80, "ws_path": "/", "host": "d36lt9hzl2ug3d.cloudfront.net"}
        if not os.path.exists(CFG_FILE): return default_cfg
        with open(CFG_FILE, 'r') as f: return {**default_cfg, **json.load(f)}

    def save_cfg(self, cfg):
        os.makedirs(os.path.dirname(CFG_FILE), exist_ok=True)
        with open(CFG_FILE, 'w') as f: json.dump(cfg, f, indent=4)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            db = self.load_db()
            config = self.load_cfg()
            
            html = f"""<!DOCTYPE html>
<html>
<head>
<title>VLESS Web Panel</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
  .container {{ max-width: 1000px; margin: auto; background: #1e293b; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }}
  h2, h3 {{ color: #38bdf8; border-bottom: 2px solid #334155; padding-bottom: 8px; }}
  .card {{ background: #0f172a; padding: 15px; border-radius: 8px; margin-bottom: 20px; border: 1px solid #334155; }}
  input, select {{ background: #1e293b; border: 1px solid #475569; color: #fff; padding: 10px; border-radius: 6px; margin: 5px 0; width: 100%; box-sizing: border-box; }}
  button {{ background: #0284c7; color: white; border: none; padding: 10px 15px; cursor: pointer; border-radius: 6px; font-weight: bold; width: 100%; }}
  button:hover {{ background: #0369a1; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
  th, td {{ padding: 12px; border-bottom: 1px solid #334155; text-align: left; font-size: 14px; }}
  th {{ background: #334155; color: #cbd5e1; }}
  .btn-sm {{ padding: 6px 10px; font-size: 12px; border-radius: 4px; text-decoration: none; display: inline-block; }}
  .btn-dl {{ background: #10b981; color: white; }}
  .btn-del {{ background: #ef4444; color: white; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
</style>
</head>
<body>
<div class="container">
    <h2>⚡ VLESS Web Panel (Transport & Config Control)</h2>
    
    <div class="card">
        <h3>⚙️ Inbound / Transport Config (Xray Settings)</h3>
        <form action='/update-config' method='POST'>
            <div class="grid">
                <div>
                    <label>Server Address / Domain:</label>
                    <input type="text" name="server_ip" value="{config.get('server_ip', '')}">
                </div>
                <div>
                    <label>Port:</label>
                    <input type="number" name="vless_port" value="{config.get('vless_port', 80)}">
                </div>
                <div>
                    <label>Path:</label>
                    <input type="text" name="ws_path" value="{config.get('ws_path', '/')}">
                </div>
                <div>
                    <label>Host Header (CloudFront/CDN):</label>
                    <input type="text" name="host" value="{config.get('host', '')}">
                </div>
            </div>
            <button type="submit" style="margin-top: 10px; background: #0d9488;">Save & Update Config</button>
        </form>
    </div>

    <div class="card">
        <h3>➕ Add New User</h3>
        <form action='/add' method='POST'>
            <div class="grid">
                <div><input type="text" name="email" placeholder="Username / Remark" required></div>
                <div><input type="date" name="expire"></div>
            </div>
            <button type="submit" style="margin-top: 10px;">Create User</button>
        </form>
    </div>

    <div class="card">
        <h3>👥 User List</h3>
        <table>
            <tr><th>Username</th><th>UUID</th><th>Expiry</th><th>Actions</th></tr>"""
            
            for u in db['users']:
                html += f"<tr><td><b>{u['email']}</b></td><td><code>{u['uuid']}</code></td><td>{u.get('expire', 'Unlimited')}</td><td><a href='/export?user={u['email']}' class='btn-sm btn-dl'>⬇ JSON</a> <a href='/remove?email={u['email']}' class='btn-sm btn-del' onclick='return confirm(\"Delete?\")'>✕ Delete</a></td></tr>"
            
            html += """</table></div></div></body></html>"""
            self.wfile.write(html.encode())

        elif parsed.path == "/export":
            query = parse_qs(parsed.query)
            email = query.get('user', [''])[0]
            db = self.load_db()
            user = next((u for u in db['users'] if u['email'] == email), None)
            config = self.load_cfg()
            
            if user:
                payload = {
                    "log": {"loglevel": "warning"},
                    "outbounds": [{
                        "protocol": "vless",
                        "settings": {
                            "vnext": [{
                                "address": config['server_ip'],
                                "port": int(config['vless_port']),
                                "users": [{"id": user['uuid'], "encryption": "none", "flow": "", "level": 8}]
                            }]
                        },
                        "streamSettings": {
                            "network": "ws",
                            "security": "none",
                            "wsSettings": {
                                "path": config['ws_path'],
                                "headers": {"Host": config['host']}
                            }
                        },
                        "mux": {"enabled": False, "concurrency": -1}
                    }],
                    "routing": {"domainStrategy": "AsIs", "rules": []}
                }
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Content-Disposition', f'attachment; filename={email}.json')
                self.end_headers()
                self.wfile.write(json.dumps(payload, indent=2).encode())
        
        elif parsed.path == "/remove":
            query = parse_qs(parsed.query)
            email = query.get('email', [''])[0]
            db = self.load_db()
            db['users'] = [u for u in db['users'] if u['email'] != email]
            self.save_db(db)
            self.send_response(303)
            self.send_header('Location', '/')
            self.end_headers()
        else:
            self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = parse_qs(self.rfile.read(length).decode())
        
        if self.path == "/add":
            db = self.load_db()
            db['users'].append({
                "email": data['email'][0],
                "uuid": str(uuid.uuid4()),
                "expire": data['expire'][0] if data.get('expire') and data['expire'][0] else "Unlimited"
            })
            self.save_db(db)
        elif self.path == "/update-config":
            cfg = self.load_cfg()
            cfg['server_ip'] = data['server_ip'][0]
            cfg['vless_port'] = int(data['vless_port'][0])
            cfg['ws_path'] = data['ws_path'][0]
            cfg['host'] = data['host'][0]
            self.save_cfg(cfg)

        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()

if __name__ == "__main__":
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    with socketserver.TCPServer(("", PORT), VlessHandler) as httpd:
        print(f"Panel running on port {PORT}")
        httpd.serve_forever()
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
