# Phase 4: Canneberge Multi-Surface Application (Desktop & Web/PWA)

> **Current Status:** Step 7 — Wiring Real Source Data Engine  
> **Active Branch:** `main`  
> **Active Directory:** `4_application/`  
> **Last Updated:** September 2, 2026  

---

## 1. Project Overview & North Star
**Project Canneberge** is a Python-based financial valuation workstation (GPC multiples, DCF modeling, Debt Schedules, FRED/StockAnalysis/yfinance data aggregators, and WACC analysis).

* **Phase 1 & 2 (Frozen):** Excel prototype and model refinement.
* **Phase 3 (Frozen):** Python ETL migration & complete PyQt6 desktop application.
* **Phase 4 (Active):** Productized multi-surface deployment.
  * **Surface A (Desktop):** PyQt6 application running locally on Windows / ChromeOS via terminal / VS Code.
  * **Surface B (Tablet / Web):** Dash-based PWA (Progressive Web App) hosted on local laptop (`0.0.0.0`) and accessed on Android tablets over home Wi-Fi in fullscreen standalone mode (no browser address bar / no Play Store requirement).

---

## 2. Core Architectural Principles
1. **Single Source of Truth (Core):** All business logic, valuation math, scrapers, and transforms live strictly in `Canneberge/`. 
2. **Thin UI Adapters:** Neither the PyQt UI nor the Dash UI contains business calculations. They only import from `Canneberge.Calculations`, `Canneberge.Sources`, etc.
3. **No Dual Logic Maintenance:** If a formula or data source changes, it is edited **once** in `Canneberge/` and automatically updates both UIs.
4. **Local Network Privacy:** No public cloud servers, no exposed personal routers, no database subscriptions. The host laptop runs the server; the tablet connects via LAN IP (`http://192.168.x.x:8050`).

---

## 3. Directory Layout (`4_application/`)

```text
4_application/
│
├── Canneberge/                   # SHARED CORE ENGINE (Untouched by UI changes)
│   ├── Calculations/             # Math, DCF, GPC, WACC, debt schedules
│   ├── Sources/                  # yfinance, FRED, StockAnalysis, MarketScreener
│   ├── Services/                 # Multi-source coordination
│   ├── Transforms/               # Data normalization / mappings
│   ├── utils/                    # Shared helper functions
│   ├── Workers/                  # Async / Threading helpers
│   ├── app_state.py              # Application dataclasses
│   └── config.py                 # API keys & configuration
│
├── desktop/                      # SURFACE A: PyQt6 Desktop UI
│   ├── Ui/                       # Existing PyQt page classes
│   └── main.py                   # Desktop entry (`python -m desktop.main`)
│
├── web/                          # SURFACE B: Dash / PWA Tablet UI
│   ├── assets/                   # CSS, icons, manifest.json (PWA configuration)
│   │   ├── manifest.json         # Makes Dash installable on Android (Fullscreen)
│   │   ├── custom.css            # Dark/Clean styling matching PyQt theme
│   │   └── icon-512.png          # App launcher icon for Android home screen
│   ├── pages/                    # Multi-page Dash routes
│   │   ├── home.py               # Ticker entry, source selection, status
│   │   ├── gpc.py                # Guideline Public Company metrics & tables
│   │   ├── dcf.py                # Discounted Cash Flow valuation
│   │   └── debt.py               # Debt schedule & capital structure
│   ├── components/               # Reusable web widgets (Navbars, Cards, Grids)
│   │   ├── navbar.py
│   │   └── metric_card.py
│   └── app.py                    # Web entry (`python -m web.app`)
│
├── requirements.txt              # All dependencies (PyQt6, Dash, Plotly, Pandas, etc.)
└── application.md                # This Gameplan
```

---

## 4. Execution Roadmap (Step-by-Step)

### Phase 4.1: Foundation & Scaffolding
- [X] **Step 1: Dependencies & Environment Setup**
  - Verify Python 3.11+ / 3.13 venv.
  - Install dependencies: `pip install dash dash-bootstrap-components pandas plotly`.
  - Update `4_application/requirements.txt`.
- [X] **Step 2: Scaffolding Directory Structure**
  - Move current `Canneberge/Ui/` into `desktop/Ui/` (or create wrappers so desktop still runs).
  - Verify desktop app runs with `python -m Canneberge.main`.
  - Create `4_application/web/` folder structure (`pages/`, `components/`, `assets/`).

### Phase 4.2: Web Skeleton & Tablet PWA Setup
- [X] **Step 3: Core Dash Shell (`web/app.py`)**
  - Initialize Dash with multi-page support (`use_pages=True`).
  - Configure top/side navigation bar for tablet touch friendliness.
  - Set host to `0.0.0.0` and port to `8050`.
- [X] **Step 4: Android PWA Configuration (`assets/manifest.json`)**
  - Add `manifest.json` with `"display": "standalone"` (removes Chrome address bar on Android).
  - Add standard application icons.
  - Test "Add to Home Screen" on Android Chrome -> opens like a native app.
- [X] **Step 5: LAN Connectivity Test**
  - Obtain Chromebook/PC LAN IP (`ip addr` or `hostname -I`).
  - Access `http://<LAPTOP_LAN_IP>:8050` from Android tablet connected to same Wi-Fi.

### Phase 4.3: Page Migration (PyQt -> Dash)
- [x] **Step 6: Home Page Conversion (`web/pages/home.py`)**
  - 1-to-1 conversion of PyQt `home_page.py`.
  - Includes **GENERAL**, **SUBJECT COMPANY**, **GPC Tickers (15 rows with yfinance name lookup)**, **GT Transactions DataTable**, and **PROJECTION CONTROLS**.
  - All input fields configured with `persistence=True` and `persistence_type="session"`.
  - Auto-sync callback updates `session-store` memory without requiring a manual save button.
- [ ] **Step 7 — Real Source Data Pipeline Integration**

**Current Problem to Solve:**
The initial prototype of `web/pages/source_data.py` was a simple `yfinance` placeholder. It **must be replaced** with Canneberge's real multi-source data architecture.

**Target Data Plumbing:**
1. **Core Service:** Must hook into `Canneberge.Services.source_data_service` and `Canneberge.Workers.source_data_worker`.
2. **Data Scrapers/APIs to Expose in Dash:**
   * `MarketScreener` (`Canneberge/Sources/marketscreener.py`)
   * `StockAnalysis` (`Canneberge/Sources/stockanalysis.py`)
   * `FRED` API (`Canneberge/Sources/fred.py`)
   * `Yahoo Finance Live` (`Canneberge/Sources/yfinance_live.py`)
   * `Beta / Volatility` (`Canneberge/Sources/beta_vol.py`)
3. **Execution Flow:**
   * Read `gpc_tickers`, `subject_ticker`, and configuration settings directly from `session-store`.
   * Execute the multi-threaded harvest pipeline.
   * Render real harvest progress, status tables, and metrics per source on the web UI.

### Phase 4.4: Hardening & Parity Check
- [ ] **Step 10: State Synchronization & Session Handling**
  - Ensure data calculated in one page persists across tabs using Dash `dcc.Store`.
- [ ] **Step 11: Final Git Checkpoint & Multi-Machine Sync**
  - Verify brother can pull on Windows and run either `python -m Canneberge.main` (desktop) or `python -m web.app` (web).

---

## 5. Developer Cheatsheet / Common Commands

### Running the Desktop App
```bash
cd ~/PampleMousseLabs/ProjectCanneberge/4_application
python -m Canneberge.main
```

### Running the Web / Tablet App (Local Host)
```bash
cd ~/PampleMousseLabs/ProjectCanneberge/4_application
python -m web.app
# Access locally: http://127.0.0.1:8050
# Access on Tablet: http://<LAN_IP>:8050
```

### Git Routine (End of Day)
```bash
git add .
git commit -m "Progress update: Phase 4 Step X"
git push
```
