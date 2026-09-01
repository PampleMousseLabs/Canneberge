# Canneberge — Project Context Brief

> Last updated: 2026-08-31

## What this is

A parametric business enterprise valuation model. Inputs flow through a defined ETL pipeline and calculation layer to produce a financial analysis report. Originally built in Excel, now a standalone Python desktop application (PyQt6), with a browser-based (Dash) version planned as the long-term primary interface.

A parametric model means: a fixed set of inputs flows through defined logic to produce a deterministic output. Any input can be adjusted to recalculate the result.

---

## Project hierarchy

Notation: Phase > Section (#.#) > Sub-topic (#.#.#) > Artifact (filename)

### Phase 1 — Excel system (frozen, reference-only)
| Section | Name | Status |
|---|---|---|
| 1.1 | Data ingestion | Complete, **stale** |
| 1.2 | Data transformation — tier 1 | Complete, **stale** |
| 1.3 | Data transformation — tier 2 | Complete, **stale** |
| 1.4 | Calculation layer | Complete, **stale** |
| 1.5 | Report output | Complete, **stale** |

> **Status note:** the Excel system is no longer maintained and should not be trusted as a live audit reference. StockAnalysis.com has changed source-table wording/structure ("Depreciation Expense" → "D&A for EBITDA" is one confirmed instance) since the Excel Power Queries were last updated, and the Excel model has not been patched to follow. Re-syncing the Excel workbook to the current source shape would mean re-writing the affected Power Queries and VBA extraction logic to match today's page structure — a real, non-trivial effort with no planned owner. Until/unless that happens, the Excel workbook is kept only as a historical reference for original methodology, not as a live cross-check against the Python app's output. Treat any Excel-vs-Python mismatch as *expected*, not a bug, unless it's freshly confirmed which side is wrong.

### Phase 2 — Refinement and documentation
| Section | Name | Status |
|---|---|---|
| 2.1 | Input reduction | Complete |
| 2.2 | Model specification | Complete |
| 2.3 | Testing and validation | Ongoing, informal (manual session-based spot checks) |

### Phase 3 — Code migration (active)
| Section | Name | Status |
|---|---|---|
| 3.1 | Tech stack selection | Complete — Python, PyQt6 desktop |
| 3.2 | ETL pipeline rebuild | Complete — StockAnalysis, MarketScreener, FRED, yfinance all live |
| 3.3 | Calculation engine rebuild | Complete for DCF/WACC/NWC/GT/GPC/Debt Schedule/Reverse-DCF; ongoing refinement |

See `3_code-migration/code-migration.md` for full detail on this phase.

### Phase 4 — Web/Tablet Access (planning)
| Section | Name | Status |
|---|---|---|
| 4.1 | Backend/data-layer decoupling | Not started |
| 4.2 | Dash web frontend | Not started |
| 4.3 | Multi-user (folder-per-user) access | Not started |
| 4.4 | Local hosting (always-on home machine) | Not started |

**Scope, decided:** home-network-only access (no public internet exposure, no VPS). One always-on host machine (old desktop, upgradeable to a dedicated device later) runs the app; other devices (tablet, Chromebook, laptop) reach it over the local network as browser clients. Desktop PyQt6 version stays as the actively-developed source; once Dash exists, PyQt6 development is expected to freeze and Dash becomes the single ongoing UI, rather than maintaining two UIs in parallel indefinitely.

---

## Ticker Capabilities

The model is an **evergreen template** — it works with whatever tickers are configured. Tickers are not hardcoded.

| Slot | Count | Source | Notes |
|---|---|---|---|
| Guideline Public Companies (GPCs) | Up to 15 | `Home` page ticker grid | User-configurable |
| Guideline Transactions (GTs) | Up to 5 (extendable) | `Home` page GT grid | Manually entered deal data |
| Subject Company | 0 or 1 | `Home` page ticker field | Only pulled from public sources when Company Status = "Publicly Traded" |

When Company Status = "Private Company," subject financials come from the Private Financials input dialog (manual entry) instead of live source pulls.

---

## Data Sources (current, Python app)

| Data | Source | Status | Notes |
|---|---|---|---|
| Income Statement, Balance Sheet, Cash Flow Statement, Ratios | StockAnalysis.com | ✅ Live | Header-driven column mapping (TTM/LFY/LFY-N), not position-based; handles short-history tickers |
| Forward Estimates (NFY/NFY+1/NFY+2: Revenue, EBITDA, EBIT, Net Income) | MarketScreener | ✅ Live | Slug resolution via POST to `async/search/quick`; subject to MarketScreener's daily rate limit |
| Interest Rates (Fed Funds, SOFR, Treasury, corporate spreads) | FRED (St. Louis Fed) | ✅ Live | Requires API key in `~/.canneberge/config.json` (never committed) |
| Beta / Volatility | yfinance (custom calc replicating Excel VBA methodology exactly) | ✅ Live | 2yr weekly / 5yr monthly beta, Blume-adjusted; volatility via log returns |
| Live market marks (price, market cap, EV, shares out) | yfinance | ✅ Live | Fast batch fetch, separate from the full historical Beta/Vol pull — used for the "Update Live Marks (2s)" session-reload option |

All four live sources are fully wired end-to-end through `Services/source_data_service.py` and `Workers/source_data_worker.py` — none are stubs as of this writing.

---

## What exists right now (Python App, Phase 3)

**11 tabs, all functional:** Home, Dashboard, WACC, DCF, NWC, Debt Schedule, GT, GPC, Subject Financials, Source Data, Analytics.

**Key architectural facts:**
- Calculation logic lives in `Calculations/` (DCF, Reverse-DCF, GPC/GT multiples, debt schedule, valuation surface, ratio catalogue, subject IS/BS calc, projection resolution, analytics/theory math) — has **no PyQt dependency**, making it portable to a future Dash backend without a rewrite.
- Session save/load is fully built (`utils/session.py`) — serializes essentially the entire app state (every page's inputs + the full cached source-data results blob) to a single JSON file. **The session file itself is the cache** — there is no separate database or persistent store; a saved session is a complete, self-contained snapshot including every prior source pull. Loading a session offers three choices: **Load Cached Data** (0s, everything frozen exactly as last saved), **Update Live Marks** (~2s, refreshes only price/market cap/enterprise value/shares outstanding via yfinance, StockAnalysis and MarketScreener data stays frozen from the save), or **Full Web Refresh** (~40s, re-scrapes all four sources fresh). This same three-way choice is also available directly from the Source Data page's refresh controls, not just at session-load time.
- Reverse-DCF (market-implied growth solver) is live, using each comparable's own observed beta (not the WACC page's re-levered beta), consistent with each ticker's own market price and capital structure.
- Projection Module supports two-way binding between typed $ values and typed growth %, tracked per-period so the app knows which one to treat as the driver.
- A StockAnalysis drift-detection prototype exists (`Prototypes/drift_tool/`) — canonical line-item ordering + a schema-drift analyzer comparing current scrapes against a reference set, aimed at catching future StockAnalysis wording changes (like the Depreciation Expense → D&A rename) before they silently break calculations.

**Known technical debt:**
- `if(CompanyStatus)` two-way binding between public/private data paths — check current state in `code-migration.md`, this may now be resolved.
- The session-file-as-cache model means there's no cache at all until you've explicitly saved a session at least once, and "freshness" is only ever as good as your last save — there's no independent, always-current cache separate from a session snapshot. Worth keeping in mind for the eventual Dash version, where multiple users/devices sharing one live data pool (rather than each pulling their own session snapshot) may call for a real shared cache layer instead.
- No installer/packaging — running the app requires a manual Python + dependency setup per machine (documented, but manual). Considered low priority given the small, known user base and the planned Dash migration, which removes the need for per-machine installs entirely.

---

## Key Conventions

| Convention | Detail |
|---|---|
| Units | Dollar values in millions USD |
| Key format | `ticker\|line item` (lowercase) |
| Zero = no data | StockAnalysis rarely returns genuine $0; treat blank/absent line items as true zero (validated against Excel historically) |
| Sessions | JSON files at `~/.canneberge/sessions/` |
| Secrets | FRED API key at `~/.canneberge/config.json`, never committed to the repo |
| `ss/` directories | Mean "superseded/deprecated" — never reference files under an `ss/` path |

---

## Live Resources

| Resource | Link |
|---|---|
| GitHub Repo | https://github.com/PampleMousseLabs/ProjectCanneberge |
| Excel Workbook (frozen reference) | [Project_Canneberge.xlsm](https://drive.google.com/drive/folders/1Uh4c7jD0-AWuaT15gkVDtA2yjFKLTphn) |
| Phase 3 detail | `3_code-migration/code-migration.md` |