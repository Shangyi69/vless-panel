#!/usr/bin/env bash
# setup.sh — VLESS Panel installer (VLESS+WS, no TLS, Mux enabled)
set -euo pipefail

PANEL_DIR="/opt/vless-panel"
PANEL_PORT=1190

echo "=== VLESS Panel Setup (WS, non-TLS) ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ ! -f "$SCRIPT_DIR/cgi-bin/panel.cgi" ]]; then
    echo "ERROR: $SCRIPT_DIR/cgi-bin/panel.cgi not found." >&2
    echo "panel.cgi must sit inside a cgi-bin/ folder next to setup.sh." >&2
    exit 1
fi

# Dirs
mkdir -p "$PANEL_DIR/cgi-bin" "$PANEL_DIR/data"

# Config
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

# Init DB
cat > "$PANEL_DIR/data/users.json" <<'EOF'
{"users": []}
EOF

# Copy CGI
cp "$SCRIPT_DIR/cgi-bin/panel.cgi" "$PANEL_DIR/cgi-bin/panel.cgi"
chmod +x "$PANEL_DIR/cgi-bin/panel.cgi"

# Redirect index
cat > "$PANEL_DIR/index.html" <<'EOF'
<!DOCTYPE html>
<html><head>
<meta http-equiv="refresh" content="0;url=/cgi-bin/panel.cgi">
</head><body></body></html>
EOF

# Systemd service
cat > /etc/systemd/system/vless-panel.service <<EOF
[Unit]
Description=VLESS Web Panel
After=network.target

[Service]
Type=simple
WorkingDirectory=$PANEL_DIR
ExecStart=python3 -m http.server --cgi $PANEL_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vless-panel
systemctl restart vless-panel

ufw allow "$PANEL_PORT/tcp" 2>/dev/null || true

echo ""
echo "Done!"
echo "  Panel : http://${SERVER_IP}:${PANEL_PORT}"
