# fastLANe ⚡️
**Windows network diagnostics** with a local UI + API — built for support, sysadmins, and “resolve in minutes” troubleshooting.

> 🧪 **UI vibe:** PlayStation-era **Final Fantasy menu** (90s JRPG).  
> Pixel-ish typography, clean HUD panels, and that “Save/Load screen energy” — but for networks. 🎛️💾
> 
> UI Inspired by https://github.com/dlcNine/rpg-css
---

## What it does
fastLANe runs **on-demand** (not a service). You launch it, it spins up a local backend and UI, you troubleshoot fast, export a report, close it.

- **Backend:** FastAPI on `127.0.0.1:9876`
- **UI:** desktop window via **pywebview** (WebView2)
- **Tabs:** Overview • Local Info • Link Discovery
- **Export:** TXT (default) + MD (optional)
- **Privacy-first:** **no telemetry**, everything stays local

---

## Features
- ✅ **Overview**
  - Quick health signal (OK/WARN/FAIL)
  - Key findings summary
  - Quick tests (ping/dns/tnc/tracert)

- ✅ **Local Info**
  - Active interface, IP/prefix, gateway, MAC
  - DNS servers, DHCP vs static
  - Link speed
  - Gateway MAC + vendor (when available)

- ⚠️ **Link Discovery (LDWin-like)**
  - Passive LLDP/CDP capture (when possible)
  - Requires **Npcap** + **Administrator**
  - If unavailable (Wi-Fi, unmanaged switch, LLDP off): shows **UNAVAILABLE** with tips

---

## Requirements (dev)
- Windows 11 / Windows Server (GUI)
- Python 3.10+ (3.11+ recommended)
- **WebView2 Runtime** (usually already on Windows 11)
- Optional: **Npcap** (for Link Discovery)
- Optional: **Inno Setup 6** (installer)

---

## Run (dev)
```bat
pip install -r requirements.txt
python run_fastlane.py
```
## API only
```
python run_fastlane.py --no-ui
```

## Build EXE (PyInstaller)

```
pyinstaller --noconfirm --onedir --windowed ^
  --icon "assets\\icon.ico" ^
  --add-data "web;web" ^
  --name fastLANe run_fastlane.py
```
Output: `dist\\fastLANe\\fastLANe.exe`

---

## Build Installer (Inno Setup)
```
"C:\\Users\\leandro\\AppData\\Local\\Programs\\Inno Setup 6\\ISCC.exe" fastLANe.iss
```
Output: `installer\\fastLANe_setup.exe`

## Npcap
Link Discovery requires **Npcap**. fastLANe detects it and shows the download link if missing.

Download: https://npcap.com/#download

Recommended install options:

* ✅ WinPcap compatibility mode (helps some capture scenarios)
---

## Troubleshooting

**UI window won’t open**: install Microsoft Edge WebView2 Runtime

**Link Discovery says "Not installed"**: reinstall Npcap with WinPcap compatibility

**Tests/capture failing**: run fastLANe as Administrator

---
## Notes
* Uses PowerShell/CLI commands without spawning extra console windows.

* UI is a local embedded WebView2 (Edge) via pywebview.

* No cloud calls, no telemetry, no surprises. 🥷
---

![Windows](https://img.shields.io/badge/Platform-Windows%2011%20%7C%20Server-0078D6?logo=windows&logoColor=white)  ![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)  ![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)  ![WebView2](https://img.shields.io/badge/UI-WebView2-0A0A0A?logo=microsoftedge&logoColor=white)  ![UI Style](https://img.shields.io/badge/UI-Final%20Fantasy%20VII%20Era-purple)

![No Telemetry](https://img.shields.io/badge/Telemetry-None-success)  ![Local Only](https://img.shields.io/badge/Data-Local%20Only-blue)  ![PowerShell](https://img.shields.io/badge/PowerShell-CLI-5391FE?logo=powershell&logoColor=white)  ![Npcap](https://img.shields.io/badge/Npcap-Optional-lightgrey)  ![PyInstaller](https://img.shields.io/badge/Packaging-PyInstaller-blue)
