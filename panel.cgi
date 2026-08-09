#!/usr/bin/env bash
# ══════════════════════════════════════════════════════
#  VLESS+WS Web Panel  —  Bash CGI
#  DB : JSON file
#  Server : python3 -m http.server --cgi
# ══════════════════════════════════════════════════════

DB="/opt/vless-panel/data/users.json"
CFG="/opt/vless-panel/data/config.json"
XRAY_CFG="/usr/local/etc/xray/config.json"
SSL_DIR="/etc/xray/ssl"

# ── Config helpers ─────────────────────────────────────
cfg_get() {
    python3 -c "
import json
try:
    c = json.load(open('$CFG'))
    print(c.get('$1', '$2'))
except:
    print('$2')
" 2>/dev/null
}

SERVER_IP=$(cfg_get server_ip "")
VLESS_PORT=$(cfg_get vless_port "443")
WS_PATH=$(cfg_get ws_path "/vless")

# ── Request parsing ────────────────────────────────────
ACTION=$(echo "$QUERY_STRING" | tr '&' '\n' | grep '^action=' | cut -d= -f2)

read_post() {
    if [[ "$REQUEST_METHOD" == "POST" && -n "$CONTENT_LENGTH" ]]; then
        POST_DATA=$(dd bs=1 count="$CONTENT_LENGTH" 2>/dev/null)
    fi
}

post_val() {
    echo "$POST_DATA" | tr '&' '\n' | grep "^$1=" | cut -d= -f2- \
    | python3 -c "import sys,urllib.parse; print(urllib.parse.unquote_plus(sys.stdin.read().strip()))"
}

get_val() {
    echo "$QUERY_STRING" | tr '&' '\n' | grep "^$1=" | cut -d= -f2- \
    | python3 -c "import sys,urllib.parse; print(urllib.parse.unquote_plus(sys.stdin.read().strip()))"
}

# ── DB operations ──────────────────────────────────────
add_user() {
    local email="$1" expire="$2" limit="$3"
    python3 - "$DB" "$email" "$expire" "$limit" <<'PY'
import sys, json
from datetime import datetime
db_f, email, expire, limit = sys.argv[1:]
import uuid
with open(db_f) as f: db = json.load(f)
db['users'].append({
    "email": email,
    "uuid": str(uuid.uuid4()),
    "created": datetime.now().strftime("%Y-%m-%d"),
    "expire": expire or "unlimited",
    "limit_gb": float(limit) if limit else 0,
    "used_gb": 0,
    "enabled": True
})
with open(db_f,'w') as f: json.dump(db, f, indent=2)
PY
}

remove_user() {
    local email="$1"
    python3 - "$DB" "$email" <<'PY'
import sys, json
db_f, email = sys.argv[1:]
with open(db_f) as f: db = json.load(f)
db['users'] = [u for u in db['users'] if u['email'] != email]
with open(db_f,'w') as f: json.dump(db, f, indent=2)
PY
}

# ── Rebuild Xray config ────────────────────────────────
rebuild_xray() {
    python3 - "$DB" "$XRAY_CFG" "$SSL_DIR" "$VLESS_PORT" "$WS_PATH" <<'PY'
import sys, json
db_f, cfg_f, ssl_dir, port, path = sys.argv[1:]
with open(db_f) as f: db = json.load(f)

clients = [
    {"id": u["uuid"], "email": u["email"], "level": 0, "flow": ""}
    for u in db.get("users", []) if u.get("enabled", True)
]

cfg = {
    "log": {"loglevel": "warning",
            "access": "/var/log/xray/access.log",
            "error":  "/var/log/xray/error.log"},
    "inbounds": [{
        "tag": "vless-ws",
        "port": int(port),
        "protocol": "vless",
        "settings": {"clients": clients, "decryption": "none"},
        "streamSettings": {
            "network": "ws",
            "security": "tls",
            "tlsSettings": {"certificates": [{
                "certificateFile": f"{ssl_dir}/cert.pem",
                "keyFile":         f"{ssl_dir}/key.pem"
            }]},
            "wsSettings": {"path": path}
        },
        "sniffing": {"enabled": True, "destOverride": ["http","tls"]}
    }],
    "outbounds": [
        {"tag": "direct", "protocol": "freedom"},
        {"tag": "block",  "protocol": "blackhole"}
    ],
    "routing": {"rules": [
        {"type":"field","ip":["geoip:private"],"outboundTag":"block"}
    ]}
}
with open(cfg_f,'w') as f: json.dump(cfg, f, indent=2)
PY
    systemctl reload xray 2>/dev/null || systemctl restart xray 2>/dev/null || true
}

# ── Client JSON export (Mux + Early Data) ─────────────
client_json() {
    local email="$1"
    python3 - "$DB" "$email" "$SERVER_IP" "$VLESS_PORT" "$WS_PATH" <<'PY'
import sys, json
db_f, email, ip, port, path = sys.argv[1:]
with open(db_f) as f: db = json.load(f)
users = [u for u in db['users'] if u['email'] == email]
if not users: sys.exit(1)
u = users[0]
out = {
    "log": {"loglevel": "warning"},
    "inbounds": [
        {"tag":"socks","port":10808,"protocol":"socks",
         "settings":{"auth":"noauth","udp":True}},
        {"tag":"http","port":10809,"protocol":"http",
         "settings":{}}
    ],
    "outbounds": [
        {
            "tag": "proxy",
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": ip,
                    "port": int(port),
                    "users": [{
                        "id": u["uuid"],
                        "encryption": "none",
                        "level": 0
                    }]
                }]
            },
            "streamSettings": {
                "network": "ws",
                "security": "tls",
                "tlsSettings": {"allowInsecure": True, "serverName": ip},
                "wsSettings": {"path": path + "?ed=2048", "headers": {}}
            },
            "mux": {"enabled": True, "concurrency": 8}
        },
        {"tag":"direct","protocol":"freedom"},
        {"tag":"block", "protocol":"blackhole"}
    ],
    "routing": {
        "domainStrategy": "IPIfNonMatch",
        "rules": [{"type":"field","outboundTag":"direct","ip":["geoip:private"]}]
    }
}
print(json.dumps(out, indent=2, ensure_ascii=False))
PY
}

# ══════════════════════════════════════════════════════
#  HTML / CSS
# ══════════════════════════════════════════════════════
CSS='
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
'

# ── Render user table rows ─────────────────────────────
user_rows() {
    python3 - "$DB" <<'PY'
import json, sys
from datetime import datetime, date

try:
    db = json.load(open(sys.argv[1]))
    users = db.get('users', [])
except:
    users = []

if not users:
    print('<tr><td colspan="6" style="text-align:center;color:#6e7681;padding:2rem">No users yet</td></tr>')
    sys.exit()

for u in users:
    em    = u.get('email','?')
    uid   = u.get('uuid','?')
    cre   = u.get('created','?')
    exp   = u.get('expire','unlimited')
    used  = float(u.get('used_gb', 0))
    limit = float(u.get('limit_gb', 0))

    # expire tag
    if not exp or exp in ('0','unlimited',''):
        exp_h = '<span class="tag ok">∞ No limit</span>'
    else:
        try:
            d = datetime.strptime(exp,'%Y-%m-%d').date()
            diff = (d - date.today()).days
            if diff < 0:
                exp_h = f'<span class="tag exp">Expired {-diff}d</span>'
            elif diff <= 7:
                exp_h = f'<span class="tag warn">{diff}d left</span>'
            else:
                exp_h = f'<span class="tag ok">{exp}</span>'
        except:
            exp_h = f'<span class="tag ok">{exp}</span>'

    # traffic bar
    if limit <= 0:
        tr_h = f'<span style="color:#6e7681">{used:.1f} GB / ∞</span>'
    else:
        pct = min(used/limit*100, 100)
        col = '#f85149' if pct>90 else '#d29922' if pct>70 else '#3fb950'
        tr_h = (f'{used:.1f}/{limit:.0f}G'
                f'<span class="bar-wrap"><span class="bar-fill" style="background:{col};width:{pct:.0f}%"></span></span>')

    print(f'''
<tr>
  <td><strong>{em}</strong></td>
  <td><code>{uid[:20]}…</code></td>
  <td style="color:#6e7681;font-size:.78rem">{cre}</td>
  <td>{exp_h}</td>
  <td>{tr_h}</td>
  <td>
    <a href="/cgi-bin/panel.cgi?action=export&user={em}"
       class="btn dl btn-sm">⬇ JSON</a>
    &nbsp;
    <form method="POST" action="/cgi-bin/panel.cgi?action=remove"
          style="display:inline"
          onsubmit="return confirm('Remove {em}?')">
      <input type="hidden" name="email" value="{em}">
      <button class="btn del btn-sm">✕</button>
    </form>
  </td>
</tr>''')
PY
}

# ── Page: Main ─────────────────────────────────────────
page_main() {
    printf "Content-Type: text/html; charset=utf-8\r\n\r\n"
    cat <<HTML
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>VLESS Panel</title>
<style>$CSS</style>
</head>
<body>
<nav class="nav">
  <h1>⚡ VLESS Panel</h1>
  <span class="badge">WS · TLS · Mux</span>
  <span class="srv">${SERVER_IP}:${VLESS_PORT}${WS_PATH}</span>
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
        <label>Traffic Limit GB (0=∞)</label>
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
$(user_rows)
    </tbody>
  </table>
</div>

</div>
</body>
</html>
HTML
}

# ── Action: Add ────────────────────────────────────────
action_add() {
    read_post
    local email; email=$(post_val email)
    local expire; expire=$(post_val expire)
    local limit;  limit=$(post_val limit_gb)
    [[ -n "$email" ]] && add_user "$email" "$expire" "$limit"
    rebuild_xray
    printf "Content-Type: text/html\r\n\r\n"
    echo '<meta http-equiv="refresh" content="0;url=/cgi-bin/panel.cgi">'
}

# ── Action: Remove ─────────────────────────────────────
action_remove() {
    read_post
    local email; email=$(post_val email)
    [[ -n "$email" ]] && remove_user "$email"
    rebuild_xray
    printf "Content-Type: text/html\r\n\r\n"
    echo '<meta http-equiv="refresh" content="0;url=/cgi-bin/panel.cgi">'
}

# ── Action: Export JSON ────────────────────────────────
action_export() {
    local email; email=$(get_val user)
    printf "Content-Type: application/json\r\n"
    printf "Content-Disposition: attachment; filename=\"%s_vless.json\"\r\n\r\n" "$email"
    client_json "$email"
}

# ── Router ─────────────────────────────────────────────
case "${REQUEST_METHOD:-GET}:${ACTION}" in
    POST:add)     action_add ;;
    POST:remove)  action_remove ;;
    GET:export)   action_export ;;
    *)            page_main ;;
esac
