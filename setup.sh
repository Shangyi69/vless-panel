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
