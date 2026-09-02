# Phase 3 — Code Migration

> Last updated: 2026-08-31
> Status: Desktop app functionally mature. Planning underway for Dash (web/tablet) migration — not yet started.

## Overview

Phase 3 replaced the Excel-based ETL pipeline and valuation model with a standalone Python desktop application. All four live data sources (StockAnalysis, MarketScreener, FRED, yfinance) are wired end-to-end, and all core valuation approaches (DCF, WACC, NWC, GT, GPC, Debt Schedule, Reverse-DCF) are implemented and in active use.

The Excel workbook (Phase 1) is now considered **frozen and stale** — see the README's Phase 1 status note. StockAnalysis.com wording drift since the Excel Power Queries were last touched means Excel can no longer be trusted as a live cross-check against this app's output. No plan currently exists to re-sync it; this app is the source of truth going forward.

The package is organized as:
- **UI Layer** (`Ui/`) — PyQt6 desktop interface, one file per tab/dialog
- **Sources** (`Sources/`) — live data fetchers, one per external source
- **Services** (`Services/`) — coordinates multi-source pulls
- **Workers** (`Workers/`) — QThread wrapper for async execution (keeps UI responsive during refresh)
- **Transforms** (`Transforms/`) — schema/period normalization
- **Calculations** (`Calculations/`) — all valuation math, **zero PyQt dependency** (this is what makes a future Dash backend a realistic reuse rather than a rewrite)
- **State** (`app_state.py`) — `ProjectInputs`, `PrivateFinancials`, `ProjectionData`, `Transaction` dataclasses
- **Utils** (`utils/`) — session save/load, StockAnalysis-specific helpers

---

## Repository Structure

```text
3_code-migration/
├── Canneberge/
│   ├── main.py                          ← Entry point (python -m Canneberge.main)
│   ├── app_state.py                     ← ProjectInputs, PrivateFinancials, ProjectionData, Transaction; IS_LINES/BS_LINES schema
│   ├── config.py                        ← Reads ~/.canneberge/config.json (FRED key, never committed)
│   ├── debug_analytics.py               ← Standalone debug/inspection script
│   ├── debug_capital_structure.py       ← Standalone debug/inspection script
│   ├── debug_reverse_dcf.py             ← Standalone debug/inspection script; mirrors Reverse-DCF extraction logic for offline testing
│   │
│   ├── Ui/
│   │   ├── main_window.py               ← Tabbed shell; owns cross-page callback wiring and save/load session logic
│   │   ├── home_page.py                 ← General/Subject/Market inputs, GPC + GT grids
│   │   ├── dashboard_page.py            ← Reconciliation of approaches, football field + candlestick charts
│   │   ├── source_data_page.py          ← Live source refresh controls + results table
│   │   ├── subject_financials_page.py   ← Subject company IS/BS (public or private path)
│   │   ├── private_financials_input_page.py  ← Manual entry dialog for private subject companies
│   │   ├── wacc_page.py                 ← WACC build-up, beta selection, capital structure
│   │   ├── dcf_page.py                  ← DCF model + Reverse-DCF dialog
│   │   ├── nwc_page.py                  ← Net working capital schedule
│   │   ├── debt_schedule_page.py        ← Debt schedule feeding projected interest expense into DCF
│   │   ├── gt_page.py                   ← Guideline Transaction comps
│   │   ├── gpc_page.py                  ← Guideline Public Company comps, dual BEV/Equity basis
│   │   ├── projection_module_page.py    ← Projection Module dialog (two-way $ / growth % binding)
│   │   ├── analytics_page.py            ← Supplementary analytics/theory views
│   │   ├── football_field_chart.py      ← Popup chart dialog
│   │   ├── gpc_candlestick_chart.py     ← Popup chart dialog
│   │   ├── valuation_surface_chart.py   ← Popup chart dialog
│   │   ├── theme.py                     ← theme_manager singleton (Slate & Gold, One Dark Pro, GitHub Light)
│   │   ├── font_scale.py                ← font_scale singleton (Ctrl+=/-/0)
│   │   └── shared_input_widgets.py      ← MultipleInputEdit, PctInputEdit, CurrencyInputEdit
│   │
│   ├── Sources/
│   │   ├── stockanalysis.py             ← IS, BS, CFS, Ratios — live
│   │   ├── marketscreener.py            ← Forward estimates — live
│   │   ├── fred.py                      ← Interest rates — live
│   │   ├── beta_vol.py                  ← Beta/volatility, replicates Excel VBA methodology exactly — live
│   │   └── yfinance_live.py             ← Fast batch live-marks fetch (price, market cap, EV, shares out) — live
│   │
│   ├── Services/
│   │   └── source_data_service.py       ← Coordinates all four source clients
│   │
│   ├── Workers/
│   │   └── source_data_worker.py        ← QThread for async pulls
│   │
│   ├── Transforms/
│   │   ├── period_mapper.py             ← TTM/LFY/LFY-N column mapping logic
│   │   └── sa_key.py                    ← StockAnalysis key-normalization helper
│   │
│   ├── Calculations/
│   │   ├── reverse_dcf.py               ← Market-implied growth solver
│   │   ├── gpc_multiples.py             ← GPC multiple selection/weighting
│   │   ├── gpc_metrics.py               ← GPC ratio computation
│   │   ├── debt_schedule.py             ← Debt schedule math
│   │   ├── valuation_surface.py         ← Sensitivity surface (WACC × LTGR grid, etc.)
│   │   ├── ratio_catalogue.py           ← Ratio definitions feeding comparable toggle tables
│   │   ├── subject_is_bs_calc.py        ← Subject company IS/BS derived-line calculations
│   │   ├── projection_resolve.py        ← Resolves Projection Module two-way-bound values
│   │   ├── analytics_math.py            ← Supplementary analytics calculations
│   │   ├── theory_math.py               ← Supplementary theory/reference calculations
│   │   └── chart_helper.py              ← Data shaping for chart consumption
│   │
│   └── utils/
│       ├── session.py                   ← save_session / load_session / list_sessions — full app-state JSON serialization
│       └── sa_utils.py                  ← Shared StockAnalysis parsing helpers (e.g. to_float)
│
├── Prototypes/
│   ├── drift_tool/                      ← StockAnalysis schema-drift detection prototype (see below)
│   ├── test_app_StockAnalysisScraper_v2.py
│   ├── test_app_MarketScreenerScraper.py
│   ├── test_app_FREDfetcher.py
│   └── test_app_Beta_Vol_Module.py
│
├── Run_Canneberge.bat                   ← Windows double-click launcher
├── requirements.txt
└── code-migration.md                    ← This file
```

---

## Completed Components

### UI Layer — all 11 tabs functional

Home, Dashboard, WACC, DCF, NWC, Debt Schedule, GT, GPC, Subject Financials, Source Data, Analytics.

**Notable UI behaviors:**
- Three-theme system (Slate & Gold, One Dark Pro, GitHub Light) switchable live from the View menu, no restart required.
- Font-scale control (Ctrl+=/-/0), independent of theme.
- Tab-change triggers recalculation of the page being switched to, so numbers are always current without a manual refresh.
- NWC always recalculates before DCF (DCF pulls Change in NWC from NWC) — enforced via `_refresh_nwc_then_dcf()` in `main_window.py`, not left to incidental ordering.
- Basis of Value (Home page) auto-syncs DCF's cash-flow basis (FCFE vs FCFF) and GPC's multiple mode (Equity vs BEV).

### Source Clients — all four live, none are stubs

| Source | Status | Notes |
|---|---|---|
| StockAnalysis | ✅ Live | Header-driven column mapping, no hardcoded years |
| MarketScreener | ✅ Live | Subject to MarketScreener's documented daily rate limit |
| FRED | ✅ Live | Reads key from `~/.canneberge/config.json` |
| yfinance (Beta/Vol) | ✅ Live | Replicates Excel VBA beta/volatility methodology exactly — do not substitute Yahoo's own reported beta, different methodology |
| yfinance (live marks) | ✅ Live | Separate, faster path for price/market cap/EV only — powers the session-reload "Update Live Marks (2s)" option |

### Session Save/Load (also functions as the data cache)

Fully built. `utils/session.py` serializes the entire app state — every page's inputs, GT/GPC/WACC/DCF/NWC/Debt Schedule/Dashboard page state, Projection Module data, private financials, and the full `source_data_results` blob from the last refresh — to one versioned JSON file (`save_session()` writes it, `load_session()` reads it straight back out).

**There is no separate cache or database.** The session JSON file *is* the cache — a complete, self-contained snapshot of everything, including every prior source pull. This is simpler than the SQLite-based caching layer once discussed as a future addition, and is the actual mechanism in production use today.

Loading a session is near-instant (state restores from the file, no network calls needed at all), then presents a three-way choice — available both at session-load time and directly from the Source Data page's own refresh controls:

| Option | Time | Behavior |
|---|---|---|
| **Load Cached Data** | 0s | Everything stays exactly as last saved — StockAnalysis, MarketScreener, FRED, Beta/Vol, all frozen. No network calls. |
| **Update Live Marks** | ~2s | Only Enterprise Value, Market Capitalization, Last Sale Price, and Shares Outstanding are overwritten via a fresh yfinance pull. StockAnalysis and MarketScreener data remain frozen from the saved session. |
| **Full Web Refresh** | ~40s | Re-scrapes all four sources (StockAnalysis, MarketScreener, FRED, Beta/Vol) fresh, same as a full Source Data page refresh. |

This is also the mechanism that made cross-machine use (e.g. moving a session file from the Windows desktop to a Chromebook install) work without any extra effort — sessions are portable JSON with no hardcoded local file paths, and the cached source data travels with the file, so a moved session is usable offline immediately via "Load Cached Data."

### Reverse-DCF

Solves for market-implied growth (Gordon Growth or H-Model) given a ticker's market cap and cost of equity. Uses each comparable's **own observed beta** (matching its own market price and capital structure) — explicitly distinct from the WACC page's re-levered beta, which normalizes GPC betas to the *subject's* target capital structure for the subject's own Ke/WACC calc. This distinction is documented directly in `main_window.py`'s `_get_reverse_dcf_inputs()` docstring and should not be "fixed" by someone who hasn't read that reasoning first.

### StockAnalysis Drift Detection (prototype)

`Prototypes/drift_tool/` contains a working prototype: canonical line-item ordering references for IS/BS/CFS/Ratios, a live scraper (`line_item_scraper.py`), and `schema_drift_analyzer.py` producing a `master_vs_scraper_drift.csv` comparing current scrapes against the canonical reference set.

This is the mechanism intended to catch future StockAnalysis wording changes — the same failure class as the historical `"market cap"` → `"market capitalization"` and `current_leases` naming bugs, and the still-open **"Depreciation Expense" → "D&A for EBITDA"** rename that currently affects `SA_KEY_MAP`-driven depreciation lookups. Promoting this from prototype to an in-app health check (per the original roadmap) is still pending, but the core detection logic already exists and works — it isn't starting from zero.

---

## Known Gaps / Technical Debt

| Item | Status |
|---|---|
| Independent/shared cache (vs. per-session snapshot) | The current cache *is* the session file — there's no cache independent of an explicit save, and no shared cache across sessions/users. Fine for single-user desktop use today. Worth revisiting once Dash exists and multiple users/devices might want to share one live data pool rather than each maintaining separate session snapshots — a real shared store (SQLite or similar) becomes more justified at that point, mainly to avoid each user separately burning MarketScreener's daily rate limit on the same tickers. |
| StockAnalysis "Depreciation Expense" → "D&A for EBITDA" rename | Confirmed drift, not yet patched into `SA_KEY_MAP`/downstream depreciation ratios. |
| Installer / packaging | None. Manual per-machine Python + `pip install -r requirements.txt` setup (documented but manual). Deliberately deprioritized — small known user base, and the problem disappears once Dash exists (no per-machine Python install needed at all for a browser client). |
| MarketScreener connection health / silent partial-data failure | MarketScreener being down or rate-limited produces a session that loads fine but with only partial forward-estimate coverage, no visible error. No in-app diagnostic for this yet. |
| Projection Module ↔ Subject Company IS/DCF/NWC wiring | Two-way $ / growth % binding exists at the Projection Module level (`ProjectionData`, `projection_resolve.py`); confirm during next working session whether this is now fully wired into Subject Company IS, DCF, and NWC, or whether that connection is still partial. |

---

## Dash / Web Migration — Planning Status

**Decided:**
- Target framework: **Dash** (Python, Flask-based), not React/FastAPI-separated-frontend. Rationale: single developer, Python-fluent, dense financial tables are well-served by `dash-ag-grid`, and staying all-Python avoids a second language/toolchain for a single-user internal tool.
- Hosting: **home network only**, no public internet exposure, no VPS. An always-on host machine (starting with an old computer, Raspberry Pi considered as a future upgrade but not cost-justified over free existing hardware) runs the Dash server; other devices reach it via local network / `localhost`.
- Multi-user: lightweight, folder-per-user session storage with a simple login gate — explicitly **not** a database-backed multi-tenant auth system, since the actual user base is two known people (not a public product).
- `Calculations/`, `Sources/`, `Services/`, `Transforms/` carry over largely as-is (no PyQt dependency) — only the UI layer (`Ui/`) requires a full rewrite, not a port, since Qt widget layout logic doesn't translate to Dash/HTML.
- PyQt6 desktop version is expected to freeze once Dash is stable, rather than maintaining both UIs in parallel indefinitely — avoids doubling every future UI-facing change across two codebases.

**Not yet started:** any actual Dash code, `dash-ag-grid` spike, a shared/persistent cache layer (if one ends up being needed — see Known Gaps above), or the login/folder-per-user mechanism.

**Recommended first step when this work begins:** one small vertical slice — a single "Refresh FRED" button wired to the existing `Sources/fred.py`, rendered in a `dash-ag-grid` table — proving the pattern end-to-end before committing to a full tab-by-tab migration. Suggested migration order once that spike works: Source Data → Home → GT → GPC → WACC → DCF → Projection Module (roughly easiest-to-hardest given current UI complexity).

---

## File Reference Quick-Link

| Purpose | File Path |
|---|---|
| Entry point | `Canneberge/main.py` |
| App state | `Canneberge/app_state.py` |
| Config / secrets | `Canneberge/config.py` |
| Main window / cross-page wiring | `Canneberge/Ui/main_window.py` |
| Session save/load | `Canneberge/utils/session.py` |
| Calculation engine | `Canneberge/Calculations/` |
| Source clients | `Canneberge/Sources/` |
| Drift detection prototype | `Prototypes/drift_tool/` |
| Launcher | `Run_Canneberge.bat` |