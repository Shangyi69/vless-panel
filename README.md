#!/usr/bin/env bash
set -euo pipefail

PANEL_DIR="/opt/vless-panel"
PANEL_PORT=1190

echo "=== VLESS Panel Setup (Native Python) ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/panel.py" ]]; then
    echo "ERROR: panel.py not found in $SCRIPT_DIR" >&2
    exit 1
fi

mkdir -p "$PANEL_DIR/data"

SERVER_IP=$(curl -s4 --max-time 5 ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
read -rp "VLESS port [443]: " VLESS_PORT; VLESS_PORT="${VLESS_PORT:-443}"
read -rp "WS path [/vless]: " WS_PATH;   WS_PATH="${WS_PATH:-/vless}"

cat > "$PANEL_DIR/data/config.json" <<EOF
{
  "server_ip":   "$SERVER_IP",
  "vless_port":  $VLESS_PORT,
  "ws_path":     "$WS_PATH"
}
EOF

if [[ ! -f "$PANEL_DIR/data/users.json" ]]; then
    echo '{"users": []}' > "$PANEL_DIR/data/users.json"
fi

cp "$SCRIPT_DIR/panel.py" "$PANEL_DIR/panel.py"
chmod +x "$PANEL_DIR/panel.py"

cat > /etc/systemd/system/vless-panel.service <<EOF
[Unit]
Description=VLESS Web Panel
After=network.target

[Service]
Type=simple
WorkingDirectory=$PANEL_DIR
ExecStart=/usr/bin/python3 $PANEL_DIR/panel.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vless-panel
systemctl restart vless-panel

ufw allow "$PANEL_PORT/tcp" 2>/dev/null || true

echo "Done! Panel is running at http://${SERVER_IP}:${PANEL_PORT}"
- **v2rayNG** → `+` → Import config from file
- **NekoBox** → Profiles → Import JSON
- **Hiddify** → Add profile → JSON

Config ထဲမှာ Mux + Early Data ပါပြီဆိုတော့ app ထဲမှာ setting ဘာမှ မထိရဘဲ connect ရတယ်။

### Remove User

`✕` button နှိပ် → confirm → removed + Xray reload

---

## File Structure

```
/opt/vless-panel/
├── cgi-bin/
│   └── panel.cgi        ← main app (bash CGI)
├── data/
│   ├── users.json       ← user database
│   └── config.json      ← server config
└── index.html           ← redirect to panel
```

```
/etc/systemd/system/vless-panel.service   ← systemd service
```

---

## Manage Service

```bash
systemctl status vless-panel
systemctl restart vless-panel
systemctl stop vless-panel
```

---

## VLESS Port Config

VLESS port / WS path ကို `/opt/vless-panel/data/config.json` မှာ ပြင်:

```json
{
  "server_ip":  "1.2.3.4",
  "vless_port": 443,
  "ws_path":    "/vless"
}
```

ပြင်ပြီးရင်:
```bash
systemctl restart vless-panel
```

> **Note:** Xray inbound port တွေကို 3x-ui panel မှာ manual configure လုပ်ရတယ်။ vless-panel က user management + config export သာ လုပ်တယ်။

---

## Client JSON (exported)

```json
{
  "outbounds": [{
    "protocol": "vless",
    "streamSettings": {
      "network": "ws",
      "security": "tls",
      "wsSettings": { "path": "/vless?ed=2048" }
    },
    "mux": { "enabled": true, "concurrency": 8 }
  }]
}
```

Mux concurrency 8 → HTTP request ~87% လျော့တယ်  
Early Data `?ed=2048` → round-trip တစ်ခု ကုန်သွားတယ်

---

## Requirements

- Ubuntu 20.04+ / Debian 10+
- Python 3 (pre-installed) — CGI script has no third-party dependencies
- Xray-core (installed separately)
- No TLS cert needed — this build runs `security: none` on the WS inbound

## Security note

Dropping TLS removes encryption **and** the traffic-shape-hiding that TLS
gives VLESS+WS (it lets your traffic look like ordinary HTTPS to network
observers). Without it, VLESS traffic on the wire is easier to fingerprint
and, since VLESS itself has no built-in encryption, easier to inspect.
This trade-off is meant for setups where the underlying transport is
already trusted or wrapped another way (private network, VPN tunnel,
already-terminated TLS elsewhere) — plan accordingly for public/hostile
networks.

---

## Author

[Shangyi69](https://github.com/Shangyi69)
