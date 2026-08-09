# vless-panel

VLESS+WS user management web panel — Pure Bash + HTML, no framework

![python](https://img.shields.io/badge/Backend-Python_CGI-3776AB?logo=python&logoColor=white)
![db](https://img.shields.io/badge/DB-JSON_file-blue)
![proto](https://img.shields.io/badge/Protocol-VLESS%2BWS%2Bno--TLS-orange)

---

## Features

- User add / remove / list
- Expire date per user (auto color: green / yellow / red)
- Traffic limit per user (GB, with visual bar)
- Client JSON export — **Mux + Early Data** ပါပြီ (v2rayNG / NekoBox import ရုံပဲ)
- Xray config auto-rebuild on every change
- Accessible via Chrome browser

## Stack

| Component | Tech |
|-----------|------|
| Backend   | Python 3 CGI (`panel.cgi`) |
| Server    | `python3 -m http.server --cgi` |
| Database  | JSON file (`users.json`) |
| Protocol  | VLESS + WebSocket, **no TLS** (`security: none`) |
| Mux       | concurrency 8 + Early Data `?ed=2048` (fewer HTTP round-trips) |

> **No TLS by design:** removing TLS drops the cert/handshake overhead
> entirely, and combined with Mux (fewer underlying HTTP connections) it
> cuts request/round-trip count further. There's a real trade-off, though —
> see [Security note](#security-note) below.

---

## Install

```bash
git clone https://github.com/Shangyi69/vless-panel.git
cd vless-panel
```

> **Important:** `setup.sh` copies the panel from `cgi-bin/panel.cgi`, so `panel.cgi`
> **must** be inside a `cgi-bin/` folder next to `setup.sh` before you run it.
> If your clone (or download) has `panel.cgi` sitting at the top level instead,
> fix it first:
> ```bash
> mkdir -p cgi-bin
> mv panel.cgi cgi-bin/panel.cgi
> ```
> Skipping this step is the most common cause of a
> `404 No such CGI script ('/cgi-bin/panel.cgi')` error after setup — `setup.sh`
> doesn't currently fail loudly if the copy source is missing.

```bash
sudo bash setup.sh
```

Setup ကတောင်းမယ်:
- VLESS port (default: `443`)
- WS path (default: `/vless`)

Server IP ကို auto-detect လုပ်တယ်။

If you already ran setup.sh and are hitting the 404, you can fix it in place
without re-running setup:
```bash
sudo mkdir -p /opt/vless-panel/cgi-bin
sudo cp cgi-bin/panel.cgi /opt/vless-panel/cgi-bin/panel.cgi
sudo chmod +x /opt/vless-panel/cgi-bin/panel.cgi
sudo systemctl restart vless-panel
```

---

## Access

```
http://YOUR_VPS_IP:1190
```

Panel port default: **1190**

---

## Usage

### Add User

Panel မှာ:
- **Username** — client name
- **Expire Date** — blank ထားရင် unlimited
- **Traffic Limit GB** — `0` ထားရင် unlimited

`+ Add` နှိပ်ရင် Xray config auto-reload ဖြစ်တယ်။

### Export Client JSON

User row မှာ `⬇ JSON` button နှိပ်ရင် download ချတယ်။

App မှာ import:
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
