3_code-migration/code-migration.md
Markdown

# Phase 3 — Code Migration

> Last updated: 2026-07-28
> Status: In Progress — Source Layer Wired, Calculation Layer Active (GT/GPC), Subject Financials + Projection Module Complete

## Overview

Phase 3 migrates the Excel-based ETL pipeline and valuation model into a standalone Python desktop application. The system preserves all functional requirements from Phase 1 while eliminating Excel/VBA dependencies, reducing runtime from ~25 minutes to target <2 minutes, and enabling future web/mobile deployment.

The Python application is organized as a modular package (`Canneberge/`) with clear separation between:
- **UI Layer** — PyQt6 desktop interface
- **Source Clients** — Data fetchers (StockAnalysis, MarketScreener, FRED, Yahoo/Beta-Vol)
- **Calculations** — Pure calculation modules, no UI dependency (GPC multiples, IS/BS roll-ups, EBITDA/EBIT derivation)
- **Services** — Coordination logic for multi-source pulls
- **Workers** — QThread wrappers for async execution
- **Transforms** — Schema normalization and period mapping
- **State** — Application inputs and configuration (`ProjectInputs`, `PrivateFinancials`, `ProjectionData`)

---

## Repository Structure

```text
3_code-migration/
├── Canneberge/                      ← Main application package
│   ├── __init__.py
│   ├── main.py                      ← Entry point (python -m Canneberge.main)
│   ├── app_state.py                 ← ProjectInputs / PrivateFinancials / ProjectionData dataclasses
│   ├── config.py                    ← Local config (FRED API key path)
│   │
│   ├── Ui/
│   │   ├── __init__.py
│   │   ├── main_window.py                    ← Tabbed shell, session save/load, cross-page wiring
│   │   ├── home_page.py                      ← General/Subject/Market inputs, GPC ticker+name grid, GT grid
│   │   ├── source_data_page.py               ← Data refresh (all 4 sources) + results table + batch progress signals
│   │   ├── subject_financials_page.py        ← Read-only IS/BS display; single source of truth for other pages
│   │   ├── private_financials_input_page.py  ← Manual IS/BS entry dialog for private subject companies
│   │   ├── projection_module_page.py         ← Forward-period projection dialog (Revenue/GP/EBITDA/D&A/CapEx)
│   │   ├── gt_page.py                        ← Guideline Transaction method
│   │   └── gpc_page.py                       ← Guideline Public Company method
│   │
│   ├── Calculations/
│   │   ├── __init__.py
│   │   ├── gpc_metrics.py           ← GPC_METRICS catalogue (display name, period, line_key)
│   │   ├── gpc_multiples.py         ← BEV computation + multiple calc for GPC comp set
│   │   └── subject_is_bs_calc.py    ← Shared IS/BS roll-up formulas (compute_is_calculated, compute_bs_calculated)
│   │
│   ├── Sources/
│   │   ├── __init__.py
│   │   ├── stockanalysis.py         ← IS, BS, CFS, Ratios scraper (multi-table union per statement)
│   │   ├── marketscreener.py        ← Forward estimates (Revenue/EBITDA/EBIT/Net Income, NFY–NFY+2)
│   │   ├── fred.py                  ← Interest rates via FRED REST API
│   │   └── beta_vol.py              ← Beta/volatility calc (yfinance price history)
│   │
│   ├── Services/
│   │   ├── __init__.py
│   │   └── source_data_service.py   ← Coordinates all 4 source clients
│   │
│   ├── Workers/
│   │   ├── __init__.py
│   │   └── source_data_worker.py    ← QThread per source, async pulls
│   │
│   ├── Transforms/
│   │   ├── __init__.py
│   │   └── period_mapper.py         ← TTM/LFY column mapping logic
│   │
│   └── utils/
│       ├── __init__.py
│       └── session.py               ← Save/load session state to JSON
│
├── Prototypes/                      ← Archived test scripts
├── Tests/                           ← Future unit/integration tests
├── Run_Canneberge.bat               ← Double-click launcher
└── code-migration.md                ← This file
```

---

## Completed Components

### UI Layer

| Component | File | Status |
|---|---|---|
| Main Window (tabbed shell) | `Ui/main_window.py` | ✅ Complete |
| Home Page (inputs) | `Ui/home_page.py` | ✅ Complete |
| Source Data Page | `Ui/source_data_page.py` | ✅ Complete — all 4 sources wired |
| Subject Financials Page | `Ui/subject_financials_page.py` | ✅ Complete — see below |
| Private Financials Input Dialog | `Ui/private_financials_input_page.py` | ✅ Complete |
| Projection Module Dialog | `Ui/projection_module_page.py` | ✅ Complete |
| GT Page | `Ui/gt_page.py` | ✅ Complete (TTM-only multiples, by design) |
| GPC Page | `Ui/gpc_page.py` | ✅ Complete (TTM + NFY/NFY+1/NFY+2 multiples) |

**Subject Financials Page — architecture note:** This page is the single source of truth for subject-company data consumed by every other page (GT, GPC, and future DCF/NWC). Key rules, established this session:
- All `is_calc=True` rows (Cost of Goods Sold, Gross Profit, Operating Expenses, EBITDA, EBIT, Pretax Income, Income Before Nonrecurring, Net Income, Debt-free Net Income) are computed locally from raw components via `Calculations/subject_is_bs_calc.py` — never read as a pre-computed value from StockAnalysis or the private-entry dialog. Exception: `total_current_liab`, `total_liabilities`, `total_equity`, `total_liab_equity` are direct StockAnalysis pulls (`BS_DIRECT_PULL_KEYS`) rather than local sums, because their raw BS components don't scrape reliably.
- EBITDA/EBIT are **never** read from StockAnalysis's own "EBITDA"/"EBIT" rows. Formula: `EBITDA = Revenue − COGS − (SG&A + R&D + Other Operating)` (deliberately excludes D&A from Operating Expenses), `EBIT = EBITDA − Depreciation − Amortization`. This applies to the subject company only — GPC comp-set tickers still use StockAnalysis's as-reported EBITDA/EBIT (deliberate methodology choice: comps should reflect what the market saw, not a recomputed figure).
- Forward periods (NFY through NFY+N) are sourced **exclusively** from the Projection Module's saved `ProjectionData` — never from MarketScreener directly. `ProjectionData` stores resolved dollar values (`revenue`, `gross_profit`, `ebitda`, `da`, `capex`) for every projection period, including the three periods (NFY/NFY+1/NFY+2) where the dialog itself sources from MarketScreener — the dialog persists the resolved number, so nothing downstream needs its own MarketScreener dependency.
- `get_historical_line_values(key, statement)` and `get_metric_value(key, period)` are the two public entry points other pages should call. GT and GPC both route subject-company metrics through `get_metric_value` — no page besides Subject Financials itself should read StockAnalysis/PrivateFinancials/MarketScreener directly for subject data.

**StockAnalysis scraper fix (this session):** `fetch_statement()` previously took only the *first* `<table>` on a page matching a row/column size filter. Confirmed live (ADBE balance sheet returns 4 `<table>` elements) that statements can split across multiple tables — assets in one, liabilities/equity in another. Fix: union rows from every table sharing the same header row as the first match.

**Session load progress (this session):** File → Open now triggers a full "Refresh All Sources" automatically and blocks (via `QProgressDialog`) until all 4 sources report complete, with live per-source progress and a running count/percentage, before showing the "Session Loaded" confirmation.

---

### Source Clients

| Source | File | Status | Notes |
|---|---|---|---|
| StockAnalysis | `Sources/stockanalysis.py` | ✅ Complete | IS, BS, CFS, Ratios; multi-table union fix applied |
| MarketScreener | `Sources/marketscreener.py` | ✅ Wired | Revenue, EBITDA, EBIT, Net Income for NFY/NFY+1/NFY+2 |
| FRED | `Sources/fred.py` | ✅ Wired | Reads API key via `config.get_fred_api_key()` |
| Beta/Vol | `Sources/beta_vol.py` | ✅ Wired | Yahoo Finance price history, 2yr weekly / 5yr monthly beta, volatility |

**StockAnalysis Features:**
- Header-driven column mapping (no hardcoded years)
- `TTM`/`LTM`/`Current` → `TTM`
- Highest `FY XXXX` → `LFY`, next → `LFY-1`, etc.
- Multi-table union per statement (see above) — required for BS totals and EBITDA/EBIT rows to resolve
- Clean null handling (`-`, `N/A`, `—`, `nan` → blank)
- Metadata columns: `Ticker`, `Key` (`ticker|line item`)

---

### Calculation Layer

| Component | File | Status |
|---|---|---|
| Subject IS/BS roll-ups | `Calculations/subject_is_bs_calc.py` | ✅ Complete |
| GPC multiples engine | `Calculations/gpc_multiples.py` | ✅ Complete |
| GPC metrics catalogue | `Calculations/gpc_metrics.py` | ✅ Complete |
| WACC | — | ⏳ Not started. Blocker (capital structure sourcing) is cleared. |
| DCF | — | ⏳ Not started |
| NAV | — | ⏳ Not started. Blocker (PBC data entry) is cleared — now user input fields, BS recovery method only. |
| NWC | — | ⏳ Not started |

---

### Services & Workers

| Component | File | Status |
|---|---|---|
| Source Data Service | `Services/source_data_service.py` | ✅ Complete — all 4 sources |
| Source Data Worker | `Workers/source_data_worker.py` | ✅ Complete |

**Worker Architecture:**
- QThread per source, async execution (UI never freezes)
- Progress signals to status label, plus batch-level `source_progress`/`all_sources_finished` signals for session-load blocking progress
- Error signals for graceful per-source failure (doesn't block the rest of a batch)

---

### Transforms

| Component | File | Status |
|---|---|---|
| Period Mapper | `Transforms/period_mapper.py` | ✅ Complete |

---

### Application State

| Component | File | Status |
|---|---|---|
| `ProjectInputs` | `app_state.py` | ✅ Complete |
| `PrivateFinancials` | `app_state.py` | ✅ Complete |
| `ProjectionData` | `app_state.py` | ✅ Complete — now stores resolved dollar values, not just drivers (see Subject Financials note above) |

---

## Execution Flow

```text
Run_Canneberge.bat
    ↓
Canneberge/main.py
    ↓
MainWindow (QMainWindow)
    ├── Home Tab (HomePage) — get_project_inputs() → ProjectInputs
    ├── Source Data Tab (SourceDataPage) — Refresh All / per-source
    ├── Subject Financials Tab — single source of truth for subject data
    ├── GT Tab — Guideline Transaction method
    └── GPC Tab — Guideline Public Company method
```

## Performance Targets

| Metric | Excel (Phase 1) | Python Target | Current Status |
|---|---|---|---|
| ETL Runtime (10 tickers) | ~25 minutes | <2 minutes | All 4 sources wired; full-batch timing not yet formally measured |
| UI Responsiveness | Frozen during refresh | Always responsive | ✅ Achieved |
| Year Mapping | Hardcoded | Dynamic from inputs | ✅ Achieved |
| Error Handling | ETL_LOG sheet | Console + UI status | ⚠️ Partial |

## Known Technical Debt (Carried from Excel)

| Item | Excel Location | Python Status |
|---|---|---|
| Hardcoded year references | `fn*.m`, `modExtraction` | ✅ Resolved in Python |
| `if(CompanyStatus)` two-way binding | `IS`, `BS` sheets | ✅ Resolved — Subject Financials branches on `is_publicly_traded` |
| MarketScreener rate limiting | Stage 0.5 VBA | ⏳ Not yet replicated (Python has no rate-limit guard yet) |

## Known Technical Debt (New, from Python migration)

| Item | Location | Status |
|---|---|---|
| `Calculations/projection_resolve.py` | New file, no longer called | Dead code — nothing references `resolve_projection_dollars` since Subject Financials switched to reading `ProjectionData` directly. Safe to delete. |
| GPC company name lookup | `home_page.py` / `gpc_page.py` | ✅ Resolved this session — `gpc_company_names` dict added to `ProjectInputs`, keyed by ticker |
| No theming / dark mode | All UI files | Queued, not started. No quick fix available — every page uses hardcoded inline `setStyleSheet()` calls; a real fix requires extracting colors into a shared theme module across ~6 files. |

## Deletion Candidates (from Excel)

| Excel Sheet | Recommendation |
|---|---|
| `Summary` | Absorb into dashboard |
| `Tax Depreciation` | Delete if not developed |
| `Amortization` | Delete if not developed |
| `NOL` | Delete (applied as discrete DCF adjustments) |
| `Market Data` | Delete (scratch use of `pmlPRICE()`) |
| `Historic Capital Structure` | Sourcing decided per Ted — ready to wire into WACC when that module is built |
| `ETL_STATE` (Sheet5) | Investigate (hidden/orphaned) |

---

## Queue (as of 2026-07-28)

Roughly ordered, not strict priority:

1. **GPC Multiples Range candlestick chart** — Open=Third Quartile, High=Maximum, Low=Minimum, Close=First Quartile, per selected metric column. Hyperlink popout on GPC page (below the "As of" date), live-bound to `stat_label_widgets` so it redraws on every `_recalculate()` (e.g. exclude-toggle). Will later also live on the Dashboard page.
2. **Light/dark mode theming** — no quick win available (see Technical Debt above). Requires extracting hardcoded colors into a shared theme module across GT/GPC/Subject Financials/Projection Module/Private Financials Input/Home pages, plus a toggle + persistence mechanism.
3. **Dashboard page** — start populating now rather than waiting for DCF/NAV/WACC to be finished. Will eventually host the GPC candlestick chart, valuation reconciliation, and other Excel `Dash_Prjctn` equivalents.
4. **WACC calculation module** — capital structure sourcing decision is made; ready to build.
5. **NAV calculation module** — PBC data entry is now user input fields; BS recovery method only; ready to build.
6. **DCF valuation engine** — not started; depends on WACC.
7. **NWC schedule** — not started.
8. **`fmv_bev` summary row** — cross-method valuation summary (DCF/GPC/GT/NAV reconciliation), correctly sequenced last since it depends on all four methods existing.

---

## Deferred: Post-Phase-3 Data Source Evaluation — EdgarTools

**Status:** Not to be started until Phase 3 is complete. Noted here so it isn't lost, not because it's near-term work.

`edgartools` (PyPI: `edgartools`, docs: https://edgartools.readthedocs.io/) is a Python library that pulls SEC EDGAR/XBRL filings directly and includes a built-in standardization layer that maps ~2,900 raw XBRL tags to a normalized set of financial statement concepts (92 distinct Balance Sheet concepts confirmed via direct inspection of the installed package's `gaap_mappings.json`, cross-referenced against `display_names.json`).

**Why this is worth evaluating later:** StockAnalysis.com scraping is fragile by nature — no published schema, label text and structure can change without notice, and completeness has already been shown to vary silently by ticker (e.g., "Minority Interest" appears for SPCX but not ADBE; "Total Common Shareholders' Equity" is a real StockAnalysis label with no equivalent in EdgarTools' standard concept set, confirmed by direct comparison). EdgarTools would source data from the same XBRL filings companies submit to the SEC, with a maintained standardization layer, removing dependency on a third-party site's presentation layer.

**Why this is NOT a straightforward swap:** EdgarTools' 92-concept Balance Sheet taxonomy is *coarser* than StockAnalysis's actual displayed line items in at least one confirmed case (Total Common Shareholders' Equity, distinct from Total Stockholders' Equity, has no EdgarTools standard concept). Switching would require rebuilding `SA_KEY_MAP`, `stockanalysis.py`, and the transform layer, and would trade "unreliable but granular" for "reliable but coarser" — not a strict upgrade. This needs a real evaluation pass against the full GPC/ticker set before any migration decision, not a default assumption that it's better.

**Action when revisited:** Compare EdgarTools' actual BS/IS output against StockAnalysis's for the full ticker universe (not just SPCX/ADBE) before deciding whether to migrate any source client.

---

## Deferred: Full IS/BS Line-Item Audit (Final Review Phase)

**Status:** Not a current priority. Current `IS_LINES`/`BS_LINES` in the Python migration are considered "good enough to get out of the starting blocks" — functional gaps will surface incrementally as new tickers are added and will be patched as found.

**Deferred work:** A full audit of `IS_LINES`/`BS_LINES` (in `app_state.py`) against actual StockAnalysis output across a wide ticker sample (target: hundreds of tickers, not the current ~9-GPC set) to confirm completeness and correct labeling. The `Line Item Needs` sheet (Excel, ~45-company empirical build) is the current best reference for expected line items and has already surfaced several gaps not yet reflected in the Python `BS_LINES` list (e.g., Total Trade Receivables, Total Long-Term Liabilities, current/long-term Unearned Revenue split, deferred tax asset/liability lines, Comprehensive Income & Other, multiple shares-outstanding variants, Working Capital).

**Action when revisited:** Treat this as final-review-phase QA, not Phase 3 blocking work. Patch individual gaps opportunistically as they're discovered during normal use in the meantime.

---

## Live Resources

| Resource | Link |
|---|---|
| Excel Workbook | `Project_Canneberge.xlsm` |
| Excel System Docs | `1_excel-system/excel-system.md` |
| Project Brief | `README.md` |