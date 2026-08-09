#!/usr/bin/env bash
# setup.sh - Optimized Installer for Native Python Panel
set -euo pipefail

PANEL_DIR="/opt/vless-panel"
mkdir -p "$PANEL_DIR/data"
# panel.py ကို /opt/vless-panel/ ထဲသို့ copy ကူးပါ
cp panel.py "$PANEL_DIR/"
chmod +x "$PANEL_DIR/panel.py"

# Systemd Service (Native Python)
cat > /etc/systemd/system/vless-panel.service <<EOF
[Unit]
Description=VLESS Web Panel
After=network.target

[Service]
Type=simple
WorkingDirectory=$PANEL_DIR
ExecStart=/usr/bin/python3 /opt/vless-panel/panel.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vless-panel
systemctl restart vless-panel
