# Phase 4: Canneberge Multi-Surface Application (Desktop & Web/PWA)

> **Current Status:** Step 8 — GPC Page (Ticker/Stats/Selected/Subject/Weighting/Bridge built; DCF page still empty placeholder)
> **Active Branch:** `main`
> **Active Directory:** `4_application/`
> **Last Updated:** September 4, 2026

---

## 1. Project Overview & North Star
**Project Canneberge** is a Python-based financial valuation workstation (GPC multiples, DCF modeling, Debt Schedules, FRED/StockAnalysis/yfinance data aggregators, and WACC analysis).

* **Phase 1 & 2 (Frozen):** Excel prototype and model refinement. Excel is stale relative to current StockAnalysis page structure — not maintained as a live cross-check anymore.
* **Phase 3 (Frozen):** Python ETL migration & complete PyQt6 desktop application. **No longer developed as a separate codebase** — see Directory Layout correction below.
* **Phase 4 (Active):** Productized multi-surface deployment.
  * **Surface A (Desktop):** PyQt6 application, still run directly out of `4_application/Canneberge/`.
  * **Surface B (Tablet / Web):** Dash-based app, hosted on a Chromebook (`0.0.0.0:8050`) and accessed from tablet/other browsers over Tailscale on the home network. HTTPS was tested and scrapped — plain HTTP over Tailscale works fine for this use case and is what's actually running.

---

## 2. Core Architectural Principles
1. **Single Source of Truth (Core):** All business logic, valuation math, scrapers, and transforms live strictly in `Canneberge/`.
2. **Thin UI Adapters:** Neither the PyQt UI nor the Dash UI contains business calculations. They only import from `Canneberge.Calculations`, `Canneberge.Sources`, etc. — confirmed holding true in practice (`web/lib/subject_metrics.py`, `web/pages/gpc.py` both delegate to `Canneberge.Calculations.*`, not reimplementing math).
3. **No Dual Logic Maintenance:** If a formula or data source changes, it is edited **once** in `Canneberge/` and automatically updates both UIs.
4. **Local Network Privacy:** No public cloud servers, no port forwarding. Tailscale connects tablet/other devices to the Chromebook host over the home network only.

---

## 3. Directory Layout (`4_application/`) — corrected to match reality

**Correction from earlier drafts of this doc:** the planned `desktop/` folder move never happened, and won't. `3_code-migration/` is frozen and untouched going forward; its contents were copied into `4_application/Canneberge/` once, and that copy is now the only actively-edited version. The PyQt6 desktop app runs directly from `4_application/Canneberge/`, same package the web app's `Canneberge.Calculations`/`Sources`/etc. imports pull from. There is no separate `desktop/` wrapper layer.

```text
4_application/
│
├── Canneberge/                   # SHARED CORE ENGINE + PyQt6 desktop UI
│   ├── Calculations/             # Math, DCF, GPC, WACC, debt schedules — shared by both UIs
│   ├── Sources/                  # yfinance, FRED, StockAnalysis, MarketScreener — all live, none stubbed
│   ├── Services/                 # Multi-source coordination
│   ├── Transforms/                # Data normalization / mappings
│   ├── utils/                    # Shared helper functions
│   ├── Workers/                  # Async / Threading helpers
│   ├── Ui/                       # PyQt6 desktop pages — run directly, not moved to a separate folder
│   ├── app_state.py              # Application dataclasses
│   └── config.py                 # API keys & configuration
│
├── web/                          # SURFACE B: Dash tablet/browser UI
│   ├── assets/
│   │   ├── manifest.json         # PWA install config (Android home-screen)
│   │   ├── custom.css            # Scrollbar overrides, misc CSS fixes — NOT yet a theme system (see Step 9)
│   │   └── (cert.pem / key.pem — leftover from an abandoned HTTPS test, unused by app.run(); candidate for deletion)
│   ├── pages/
│   │   ├── home.py               # ✅ Built — full 1:1 conversion of desktop Home page
│   │   ├── source_data.py        # ✅ Built — real multi-source pipeline (see Step 7 note below)
│   │   ├── subject_financials.py # ✅ Built — public/private branching via shared Calculations
│   │   ├── gpc.py                # ✅ Built — Ticker grid, Statistics, Selected Multiples, Subject,
│   │   │                          #    Weighting, Bridge-to-Equity. See Step 8 notes for real gaps.
│   │   └── dcf.py                # Empty placeholder file (proves nav routing only — same pattern
│   │                              #   gpc.py itself started as). Real DCF page not yet built.
│   ├── components/
│   │   └── projection_modal.py   # ✅ Built — two-way $/% binding, real scrolling (fixed this session)
│   └── app.py                    # Web entry (`python -m web.app`)
│
├── requirements.txt
└── 4_application.md              # This document
```

**Note on `web/lib/`** (not shown above, exists alongside `pages/`/`components/`): `subject_metrics.py`, `session_io.py`, `ui_layout.py` — the thin-adapter layer that bridges Dash pages to `Canneberge.Calculations`. This is where the architecture's "single source of truth" principle is actually enforced, not just stated.

---

## 4. Execution Roadmap (Step-by-Step)

### Phase 4.1: Foundation & Scaffolding — Complete
- [X] **Step 1: Dependencies & Environment Setup**
- [X] **Step 2: Scaffolding** — *(corrected: no `desktop/` split happened — see Directory Layout above)*

### Phase 4.2: Web Skeleton & Tablet Access — Complete
- [X] **Step 3: Core Dash Shell (`web/app.py`)** — multi-page, `use_pages=True`, running on `0.0.0.0:8050`.
- [X] **Step 4: Android PWA Configuration** — `manifest.json` in place.
- [X] **Step 5: Tablet Connectivity** — resolved via **Tailscale**, not raw LAN IP as originally planned. Tested working from Chromebook's own browser and from tablet Chrome, both over the Tailscale tunnel. HTTPS (`cert.pem`/`key.pem`) was tried and abandoned — plain HTTP over Tailscale's already-encrypted tunnel was sufficient and simpler.

### Phase 4.3: Page Migration (PyQt → Dash) — In Progress
- [X] **Step 6: Home Page** — complete.
- [X] **Step 7: Real Source Data Pipeline** — complete, not a placeholder. `web/pages/source_data.py` is fully wired to `Canneberge.Services.source_data_service` with per-source refresh buttons, a combined "Refresh All," background execution via `DiskcacheManager`, and live progress callbacks. *(Correction: an earlier draft of this doc described this as still using a yfinance-only placeholder — that was stale even at the time it was written; verified against actual file contents.)*
- [X] **Step 7b: Subject Financials** — complete, correctly branches public/private company status, reads through shared `Calculations.subject_is_bs_calc`.
- [X] **Step 7c: Projection Module** — complete. Two-way $/% binding for Revenue/EBITDA/D&A/SBC/Other Amortization/Net Income, MS-covered-period analyst-wins logic, "+Other Adjustments" plug for the EBITDA→NI bridge (only for NFY–NFY+2). Real horizontal scrolling fixed this session (root cause: `<table>` elements don't reliably respect `width: max-content` cross-browser — fixed with an explicit pixel-width + `overflow-x` container approach, plus ChromeOS/Linux Chrome's auto-hiding overlay scrollbars needed an explicit `::-webkit-scrollbar` CSS override to be visible/grabbable at all).
- [ ] **Step 8: GPC Page** — largely built, real gaps remain:
  - ✅ Controls (How Many Multiples spinbox, Basis toggle, DLOC%, Control Premium% inputs)
  - ✅ Ticker grid — metric-picker dropdowns embedded as literal `<th>` header cells (not a separate control row) for guaranteed column alignment; exclude checkboxes with persisted state
  - ✅ Statistics (Max/Q3/Avg/Median/Q1/Min, computed over non-excluded tickers only, headerless — inherits position from the ticker grid's dropdowns above)
  - ✅ Selected Multiples (High/Low, pre-filled from Median, user-editable)
  - ✅ Subject Company section — subject's own metric per column via `get_subject_metric_value()`, Indicated BEV High/Low
  - ⚠️ Weighting section — renders and displays equal-weight defaults, but **typed weight overrides are not yet live-wired into the FMV calculation** (equal weighting is hardcoded as a stopgap). Needs `Input({"type": "gpc-weight", "index": ALL}, "value")` added to the render callback.
  - ⚠️ Bridge section — **BEV-mode formula chain only**. Desktop's Equity-mode branch (`eq_nctrl` → `eq_mkt_ctrl` → `eq_nonmkt_ctrl`) is not ported; the bridge currently always computes as if BEV mode regardless of the Basis toggle.
  - ⚠️ **Private-company cash path stubbed to `None`** in the Bridge — desktop reads `PrivateFinancials.get_bs("cash", "TTM")` for private subjects; the web app's private-financials data path for this specific value hasn't been traced/wired yet.
  - ⚠️ NWC Surplus/Deficit and Non-Operating Assets, Net remain manual placeholder inputs (matches desktop — these were never computed automatically there either).
  - ⚠️ Company Name column in the ticker grid is blank — desktop pulls this from Home page's per-ticker yfinance lookup; not yet piped into the GPC page.
- [ ] **Step 9: Theme System** — not started. Real finding from this session: the web app's current dark styling (via Bootstrap DARKLY) doesn't match desktop's *default* theme (Slate & Gold, which is light-background) — it coincidentally resembles desktop's **One Dark Pro** theme instead. Before building more pages, extract `theme.py`'s actual named color roles (`input_bg`, `input_text`, `note_text`, `locked_text`, `pct_input_bg`/`pct_input_text`, header styles — for all three themes) into CSS custom properties in `custom.css`, and reference `var(--input-bg)` etc. going forward instead of the ad hoc hardcoded hex currently scattered through `gpc.py` and `custom.css`. Decide explicitly whether "match desktop" means matching the true default (Slate & Gold) or standardizing on the dark option (One Dark Pro) the web app already resembles.
- [ ] **Step 10: DCF Page** — not started beyond the empty placeholder file. Real build needed: full projected IS/BS grid, Terminal Value panel (Gordon Growth / H-Model / EBITDA Multiple / Revenue Multiple), Sensitivity Table, Reverse-DCF dialog. Two real bugs were found and fixed **in the desktop app's underlying `valuation_surface.py`/`dcf_page.py` this session** (EBITDA Multiple terminal value used `final_fcf` instead of `final_ebitda`; H-Model's sensitivity-table math used an approximated residual FCF instead of the real pipeline-computed one) — since `Calculations/` is shared, these fixes apply automatically once the web DCF page is built against the same engine; they don't need separate porting.
- [ ] **Step 11: Debt Schedule, NWC, WACC, GT pages** — not started.

### Phase 4.4: Hardening & Parity Check — Not Started
- [ ] State synchronization confirmed working for Home/Subject Financials/Source Data/GPC via `dcc.Store` (`session-store`, `source-results-store`) — extend same pattern to remaining pages as built.
- [ ] Final multi-machine sync check (brother's Windows machine, per Phase 3 handoff notes) — not yet re-verified against the current `4_application/` structure.

---

## 5. Known Issues / Technical Debt Log

| Item | Status |
|---|---|
| `cert.pem` / `key.pem` in `web/assets/` | Unused leftovers from an abandoned HTTPS test. `app.run()` doesn't reference them. Candidate for deletion. |
| `web/components/navbar.py` | Empty file — `app.py` builds its navbar inline instead. Dead scaffolding, not a bug. |
| GPC Weighting inputs | Render but don't feed live values into FMV calc yet (equal-weight hardcoded). |
| GPC Bridge — Equity mode | Not ported; only BEV-mode formula chain exists. |
| GPC Bridge — private-company cash | Stubbed to `None`; desktop's `PrivateFinancials` path not yet wired. |
| GPC ticker grid — Company Name column | Blank; desktop's per-ticker name lookup not yet piped in. |
| Theme system | Not started — see Step 9. Hardcoded hex colors scattered per-file need consolidating before more pages are built, to avoid a large retrofit later. |
| `dcc.Dropdown` dark-theme styling | Resolved this session via `dbc.min.css` CDN bridge + `className="dbc"` on dropdowns — document this pattern for reuse on any future page using `dcc.Dropdown`. |
| Input-in-table-cell right-alignment | Resolved this session — `dbc.Input` renders as a Bootstrap block-level `.form-control`; `text-align` on the parent `<td>` does nothing for a block-level child. Fix is `marginLeft: "auto"` on the **input's own** style, not the cell's. |

---

## 6. Developer Cheatsheet / Common Commands

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
# Access on tablet/other devices: http://<tailscale-ip>:8050
```

### Git Routine (End of Day)
```bash
git add .
git commit -m "Progress update: Phase 4 Step X"
git push
```