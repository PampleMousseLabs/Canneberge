# Phase 4: Canneberge Multi-Surface Application (Desktop & Web/PWA)

> **Current Status:** One-file workflow achieved. Same `~/.canneberge/sessions/*.json` opens on both surfaces. Session-schema adapter complete (desktop-canonical on disk, web translation in memory). Desktop Projection Module now calls shared `resolve_projection_dollars()` — 5/5 match. Desktop DCF now calls shared `build_dcf()` + `fv_for_assumptions()` — grid, TV, bridge, sensitivity match on both Equity/FCFE/Ke and BEV/FCFF/WACC. Shared `gpc_metrics.py` line_key fix repairs desktop GPC + web GPC + Dashboard at once. Remaining: NWC/WACC desktop port-back (optional — inputs already tie), dead `_populate_*` removal, Dash input-remount UX, Theme.
> **Active Branch:** `main`
> **Active Directory:** `4_application/`
> **Last Updated:** September 7, 2026

---

## 1. Project Overview & North Star

**Project Canneberge** is a Python-based financial valuation workstation (GPC multiples, DCF modeling, Debt Schedules, FRED/StockAnalysis/yfinance data aggregators, and WACC analysis).

* **Phase 1 & 2 (Frozen):** Excel prototype and model refinement. Excel is stale relative to current StockAnalysis page structure — not maintained as a live cross-check anymore.
* **Phase 3 (Frozen):** Python ETL migration & complete PyQt6 desktop application. **No longer developed as a separate codebase** — see Directory Layout correction below.
* **Phase 4 (Active):** Productized multi-surface deployment.
  * **Surface A (Desktop):** PyQt6 application, still run directly out of `4_application/Canneberge/`.
  * **Surface B (Tablet / Web):** Dash-based app, hosted on a Chromebook (`0.0.0.0:8050`) and accessed from tablet/other browsers over Tailscale on the home network. HTTPS was tested and scrapped — plain HTTP over Tailscale works fine for this use case and is what's actually running.
  * **Sept 7 rule:** one canonical file per deal in `~/.canneberge/sessions/` (e.g. `ADBE.json`). No `*_desktop.json` / `*_web.json` pair maintenance. Web converts on load/save; desktop merges on save to preserve web-only keys.

---

## 2. Core Architectural Principles

1. **Single Source of Truth (Core):** All business logic, valuation math, scrapers, and transforms live strictly in `Canneberge/`.
2. **Thin UI Adapters:** Neither the PyQt UI nor the Dash UI should contain business calculations. They import from `Canneberge.Calculations`, `Canneberge.Sources`, etc.
   * **Web is there:** `web/lib/subject_metrics.py`, `web/lib/nwc_data.py`, `web/lib/wacc_data.py`, `web/lib/dcf_data.py`, `web/lib/gt_data.py`, `web/lib/dashboard_data.py`, and the corresponding pages all delegate to `Canneberge.Calculations.*`.
   * **Desktop is now there for Projection + DCF (Sept 7):** `Ui/projection_module_page.py` harvests widgets then calls `resolve_projection_dollars()`; `Ui/dcf_page.py` collects inputs then calls `build_dcf()` / `fv_for_assumptions()` and renders `self._shared_calc`. Old `_populate_*` DCF methods are bypassed but not deleted (rollback safety).
   * **Desktop still local but tying out:** `Ui/nwc_page.py`, `wacc_page.py` still contain local math; inputs match and outputs tie on `ADBE.json`, so port-back is optional cleanup, not a parity blocker. `Ui/gt_page.py` was already byte-identical to web (`gt_page_state` had zero diff) — no port needed.
3. **No Dual Logic Maintenance:** If a formula or data source changes, it is edited **once** in `Canneberge/` and should update both UIs.
   * **Working rule:** any change that touches definitions, schema (`IS_LINES` / `BS_LINES`), or resolvers goes into `Canneberge/` first; `web/` only gets “make it render” edits.
   * **Sept 7 proof:** one `gpc_metrics.py` line_key fix (`ebitda` → `adj_ebitda`) repaired desktop GPC, web GPC, and Dashboard simultaneously.
4. **Headless page resolvers (web):** Dashboard and DCF must **never** `import web.pages.*` inside a callback. Importing a Dash page re-runs `dash.register_page()` and crashes. Cross-page reads go through `web/lib/*_data.py`.
5. **Local Network Privacy:** No public cloud servers, no port forwarding. Tailscale connects tablet/other devices to the Chromebook host over the home network only.
6. **Canonical session (Sept 7):** On-disk format is desktop-shaped (lists, 7-slot GPC, 15-row exclusions, `x`/`%` suffixes). Web translates to dicts/clean numbers in memory and back on save. Both surfaces preserve unknown extension keys. Derived caches (`wacc_value`, `changes_in_nwc`, `fv_base`, …) are stripped on save and recomputed on load.

---

## 3. Directory Layout (`4_application/`) — corrected to match reality

**Correction from earlier drafts of this doc:** the planned `desktop/` folder move never happened, and won't. `3_code-migration/` is frozen and untouched going forward; its contents were copied into `4_application/Canneberge/` once, and that copy is now the only actively-edited version. The PyQt6 desktop app runs directly from `4_application/Canneberge/`, same package the web app's `Canneberge.Calculations` / `Sources` / etc. imports pull from. There is no separate `desktop/` wrapper layer.

```text
4_application/
│
├── Canneberge/                   # SHARED CORE ENGINE + PyQt6 desktop UI
│   ├── Calculations/
│   │   ├── subject_is_bs_calc.py # EBIT / EBITDA / Adj EBITDA / net_interest
│   │   ├── projection_resolve.py # resolve_projection_waterfall() + resolve_projection_dollars() — now called by BOTH UIs
│   │   ├── debt_schedule.py      # Tranche interest / ending debt / net borrowing
│   │   ├── nwc.py                # subject NWC, peer DFCFNWC, stats, bridge
│   │   ├── wacc.py               # betas, Ke, Kd, rounded WACC
│   │   ├── dcf.py                # build_dcf() / fv_for_assumptions() / sensitivity_grid() — now called by BOTH UIs
│   │   ├── gt.py                 # transaction multiples, indicated BEV, equity bridge
│   │   ├── gpc_metrics.py        # ✎ Sept 7 FIX — NFY Adj EBITDA line_key ebitda → adj_ebitda (fixes both UIs + Dashboard)
│   │   ├── gpc_multiples.py      # Comp-side multiples
│   │   ├── ratio_catalogue.py    # Debt/TIC, historic structure, effective tax
│   │   ├── reverse_dcf.py        # Reverse-DCF solvers (Gordon / H-Model)
│   │   ├── valuation_surface.py  # Sensitivity / surface FV evaluator
│   │   └── chart_helper.py       # MethodRow bridge + football-field inputs
│   ├── Sources/                  # yfinance, FRED, StockAnalysis, MarketScreener
│   ├── Services/                 # Multi-source coordination
│   ├── Transforms/               # sa_key.py — SBC / other_amortization are CFS-sourced
│   ├── utils/
│   │   └── session.py            # ✎ Sept 7 — deep-merge save + _canonicalize_gpc_for_desktop() on load
│   ├── Workers/
│   ├── Ui/                       # PyQt6 desktop pages
│   │   ├── projection_module_page.py # ✎ Sept 7 — thin: calls resolve_projection_dollars(), EBIT/Net Interest rows added
│   │   ├── dcf_page.py           # ✎ Sept 7 — thin renderer: calls build_dcf(), _shared_calc, +Other Adjustments row
│   │   ├── gpc_page.py           # unchanged — fixed via shared gpc_metrics.py
│   │   └── main_window.py        # ✎ Sept 7 — projection other_adj collect/apply, interest callbacks, DCF refresh order
│   ├── app_state.py              # IS_LINES / BS_LINES / dataclasses (ProjectionData.other_adj already existed)
│   └── config.py
│
├── web/                          # SURFACE B: Dash tablet/browser UI
│   ├── assets/
│   │   ├── manifest.json
│   │   └── custom.css            # Compact control strips
│   ├── lib/                      # Headless adapters — no Dash page imports
│   │   ├── subject_metrics.py    # Historical + projection metric resolver
│   │   ├── session_io.py         # ✎ Sept 7 — bidirectional adapter (gpc_to_web/deskit, strip_derived_caches)
│   │   ├── nwc_data.py           # Residual revenue + NWC schedule
│   │   ├── wacc_data.py          # on-the-fly WACC / Ke
│   │   ├── dcf_data.py           # on-the-fly DCF (Dashboard-safe)
│   │   ├── gt_data.py            # GT adapter + formatters
│   │   ├── dashboard_data.py     # recon, bridge, football-field rows
│   │   └── ui_layout.py
│   ├── pages/
│   │   ├── home.py
│   │   ├── source_data.py
│   │   ├── subject_financials.py
│   │   ├── debt_schedule.py
│   │   ├── nwc.py
│   │   ├── wacc.py
│   │   ├── dcf.py                # 26-row waterfall (incl. +Other Adjustments in FCFE)
│   │   ├── gt.py
│   │   ├── gpc.py                # NWC surplus wired; range chart; Equity indicated parse fix
│   │   └── dashboard.py          # control dashboard, not a report
│   ├── components/
│   │   ├── projection_modal.py
│   │   ├── reverse_dcf_modal.py
│   │   └── gt_range_chart.py     # Plotly candlestick reused by GT + GPC
│   └── app.py                    # Nav: Home, Dashboard, Subject Financials, Source Data,
│                                 #      Debt Schedule, NWC, WACC, GT, GPC, DCF
│
├── requirements.txt
└── 4_application.md              # This document
```

---

## 4. Execution Roadmap (Step-by-Step)

### Phase 4.1: Foundation & Scaffolding — Complete

- [X] **Step 1: Dependencies & Environment Setup**
- [X] **Step 2: Scaffolding** — *(corrected: no `desktop/` split happened — see Directory Layout above)*

### Phase 4.2: Web Skeleton & Tablet Access — Complete

- [X] **Step 3: Core Dash Shell (`web/app.py`)** — multi-page, `use_pages=True`, running on `0.0.0.0:8050`.
- [X] **Step 4: Android PWA Configuration** — `manifest.json` in place.
- [X] **Step 5: Tablet Connectivity** — Tailscale, plain HTTP. HTTPS abandoned.

### Phase 4.3: Page Migration (PyQt → Dash) — Complete

- [X] **Step 6: Home Page** — complete.
- [X] **Step 7: Real Source Data Pipeline** — complete. Wired to `Canneberge.Services.source_data_service`, per-source refresh, Refresh All, `DiskcacheManager`, live progress.
- [X] **Step 7b: Subject Financials** — complete. Shared `compute_is_calculated` / `IS_LINES`. Compact IS/BS toggles. Projected interest expense displayed negative in the **display layer only**; plumbing stays a positive cost so Projection Module EBIT math is unchanged. CFS SBC and Other Amortization feed Adjusted EBITDA.
- [X] **Step 7c: Projection Module** — complete. True statement waterfall: Adjusted EBITDA → Less D&A → Less Other Amort → Less SBC → EBIT → Net Interest → +Other Adjustments (pre-tax plug) → Taxes → Net Income → CapEx. Debt Schedule interest wired. Historical taxes = reported, not statutory × pretax.
- [X] **Step 7d: Income-Statement Definition Consolidation** — complete in shared core, **desktop drift eliminated Sept 7**.
  - `EBIT = GP − OpEx`
  - `EBITDA (before SBC add-back) = EBIT + D&A + Other Amortization`
  - `Adjusted EBITDA = EBITDA + SBC`
  - Desktop Projection + DCF now call the same resolvers; TTM anchor is Adj EBITDA on both surfaces.
- [X] **Step 8: GPC Page** — complete for BEV workflow; **Sept 7 BEV subject-metrics fix** (shared `gpc_metrics.py` line_key). Remaining gaps listed under ⚠️.
  - Compact control strip; Home `basis_of_value` hydrates the starting toggle; local BEV/Equity still works.
  - `basis_state.BEV` / `basis_state.EQUITY` isolate `metric_cols`, selected multiples, and weights. Slice-aware persist (`ctx.triggered_id`) so a basis toggle cannot wipe the destination bucket.
  - `_safe_dict()` prevents crashes on legacy list-shaped session data.
  - Single shared `<table>` + `<colgroup>` for header/body alignment.
  - Forward subject metrics resolve `"adj_ebitda"` for NFY / NFY+1 / NFY+2 on **both** UIs (was web-only; desktop fixed via shared file).
  - **NWC Surplus/(Deficit)** is now read-only and sourced from `nwc_page_state["surplus_deficit"]` (no longer a manual placeholder).
  - **GPC Multiples Range Chart** pop-out (Plotly candlestick: Open=Q3, High=Max, Low=Min, Close=Q1). Reuses `web/components/gt_range_chart.py`.
  - Selected-multiple parser now strips `"x"` so Equity indicated values calculate (`"15.00x"` no longer becomes `0.0` / NA).
  - ⚠️ Bridge — BEV-mode formula chain only. Desktop Equity-mode branch (`eq_nctrl` → `eq_mkt_ctrl` → `eq_nonmkt_ctrl`) not ported.
  - ⚠️ Private-company cash path stubbed to `None`.
  - ⚠️ Non-Operating Assets, Net remains a manual placeholder.
  - ⚠️ Company Name column can still be blank if Home never wrote `gpc_company_names`.
  - ⚠️ `"TTM EBITDA"` label text preserved for session compat but now resolves to `adj_ebitda` under the hood (label debt — see Known Issues).
- [X] **Step 11a: Debt Schedule** — complete. Shared `Calculations/debt_schedule.py`. Desktop-compatible `debt_page_state` plus cached `interest_expense_by_period` / `ending_debt_by_period` / `net_borrowing_by_period`. Fallback recompute from tranche rows if caches missing.
- [X] **Step 11b: NWC** — complete.
  - Shared `Canneberge/Calculations/nwc.py`; desktop page left untouched (ties out, port optional).
  - **Option A preserved:** Cash Treatment affects GPC peer NWC only. Subject NWC is always selected CA − selected CL. Negative NWC preserved (`-4.2%` stays negative; adapter only adds/strips `%`).
  - Local Historical Years; global Projection Years (synced with Home).
  - TTM is a real column so NFY ΔNWC = NFY NWC − TTM NWC.
  - Residual column exists; Residual Revenue = final projected revenue × (1 + DCF LTGR) via `dcf.residual_revenue()` so DCF can consume `changes_in_nwc["Residual"]` without a circular page import.
  - Turnover Ratios basis blanks projected NWC (no projected BS).
  - GPC peer table, stats, Selected %, Normalized / Actual / Surplus/(Deficit), combo chart.
  - State compatible with desktop `collect_state()` plus web caches (`changes_in_nwc`, `surplus_deficit`, …).
- [X] **Step 11d: WACC** — complete.
  - Shared `Canneberge/Calculations/wacc.py`; desktop page left untouched (ties out, port optional).
  - Comp table, stats, Selected Debt%TIC / Tax (read-only Home rate) / Re-Levered Beta.
  - MCAPM Ke, FRED pretax Kd, after-tax Kd, We/Wd, WACC **rounded to 4 decimals** (2 dp as a percent) — that rounded value is what DCF consumes.
  - Preserved: magnitude percent parse (`5` → 5%, `0.5` → 50%); book vs market Debt/TIC by Capital Structure dropdown; Ke requires all four terms (blank Size Premium → NA, not 0).
  - `web/lib/wacc_data.py` is page-independent so DCF/Dashboard never import `web.pages.wacc`.
- [X] **Step 10: DCF Page** — complete on web; **desktop parity completed Sept 7** (was placeholder → web-only → now both).
  - Shared `Canneberge/Calculations/dcf.py` + `web/lib/dcf_data.py` (Dashboard-safe; no `web.pages.dcf` import). Desktop `_recalculate()` now calls `build_dcf()` and renders `self._shared_calc`; sensitivity calls `fv_for_assumptions()`.
  - 26-row waterfall (25 + P&L `+Other Adjustments`), no TTM column, Residual column, four TV models (Gordon / EBITDA Multiple / Revenue Multiple / H-Model), FV bridge, 5×5 sensitivity heatmap.
  - **Former “approved deviations” are now eliminated — desktop matches web:**
    - EBITDA row is **Adjusted EBITDA** on both (desktop label rewritten to “Adjusted EBITDA” at render; internal row key `"EBITDA"` preserved for compat).
    - Full precision on both (desktop no longer re-parses rounded QLabel text; bridge uses `calc["sum_pv_fcf"]` / `calc["pv_residual"]` / `calc["fv_base"]`).
    - Sensitivity **re-discounts explicit-period FCFs** at the column rate on both (desktop lopsided heatmap fixed).
  - FCFE shows Net Interest and Projection Module **+Other Adjustments** so EBT − SBC + OA − Taxes foots to Net Income. P&L OA row hidden in FCFF; hidden row still in `calc["rows"]`.
  - FCF `Less: Other Adjustments` remains the cash-flow add-on (acquisitions / user plug), distinct from the P&L OA row.
  - Desktop `sf("other_adj")` reads `ProjectionData.other_adj` (same source as web), not Subject Financials / StockAnalysis.
  - Home Basis of Value overrides Cash Flows to (Equity → FCFE/Ke, BEV → FCFF/WACC) on both.
  - Reverse-DCF modal/dialog untouched by this work (web modal + desktop dialog both pre-existing).
  - 3D Valuation Surface omitted on web; desktop hyperlink is unreachable tech debt.
- [X] **Step 11c: GT Page** — complete. Zero-diff on session compare — no adapter or port needed.
  - Shared `Canneberge/Calculations/gt.py` + `web/lib/gt_data.py`.
  - GPC-style layout: split header/body callbacks, sibling Statistics / Selected / Subject / Weighting tables, separate Bridge card.
  - Transactions owned by Home; analysis only on GT.
  - DLOC field is read-only; Dashboard Control Premium is source of truth (`DLOC = CP / (1 + CP)`). Until Dashboard writes it, saved `gt_page_state.dloc` is used.
  - Range chart modal (Q3/Max/Min/Q1 candlestick).
- [X] **Step 12: Dashboard** — complete as a **control dashboard**, not a report.
  - Income Approach: WACC fields (Debt/TIC + Beta with Median/Custom stats, ERP, Size, CSRP, pretax series, WACC output) and DCF options (TV model, LTGR, multiple / H-Model fields, Dep % of CapEx).
  - Market Approach: GPC (up to 7) and GT (up to 3) metric / low / high / weight rows; How Many resets even weights.
  - Reconciliation: DCF / GPC / GT / GIPO / NAV; Control Premium → Implied DLOC; Display BEV / Equity / $/Share; Concluded FV; Observed EV / Market Cap / Share Price.
  - Cost Approach: layout + persisted inputs only (NAV not calculated).
  - Football-field chart (Plotly): one bar per method line, observed marker, concluded FV line.
  - Two-way last-edit-wins via **session-store** (`wacc_page_state`, `dcf_page_state`, `gpc_page_state`, `gt_page_state`, `dashboard_page_state`). Dash cannot bind live PyQt widgets across unmounted pages.
  - Illegal `import web.pages.dcf` inside callbacks was the blank-Dashboard crash (`dash.register_page() can't be called within a callback`). Fixed by `web/lib/dcf_data.py`.
- [ ] **Step 9: Theme System** — not started. Web DARKLY ≈ desktop One Dark Pro, not Slate & Gold. Extract `theme.py` roles to CSS custom properties. Shared scroll-container helper still pending.

### Phase 4.4: Hardening & Parity Check — Substantially Complete (Sept 7)

- [X] Web pages listed above persist through `dcc.Store` / `session-store`.
- [X] **Web ↔ desktop session JSON equivalent (Sept 7).** One canonical file. Desktop-shaped GPC on disk; web translates both directions; desktop deep-merges on save to preserve web-only keys.
  - Envelope identical (13 top-level keys). `gt_page_state` zero-diff.
  - GPC: `metric_selections`↔`metric_cols`, `excluded_rows`↔`exclude_map` (positional via `project_inputs.gpc_tickers`), `per_basis_state`↔`basis_state` (`metrics/low/high` ↔ `metric_cols/selected_low/selected_high`), `last_basis_mode`↔`basis_mode`. All 7 slots preserved even when `num_multiples=6`. `"x"`/`"%"` suffixes added on save, stripped on load.
  - Legacy web-shaped files (`metric_cols`/`basis_state`/`exclude_map` already on disk) detected via `_is_desktop_gpc_shape()` — dict keys `"0".."6"` no longer misread as values (`0x/1x/2x` bug fixed).
  - Web-only inputs preserved across desktop save: `projection.other_adj`, `gpc.nwc`/`non_op`, `dashboard.debt_tic_stat`/`beta_stat`/`cost_count`/`cost_values`, `dcf.nols`/`bridge_other_adj`/`valuation_approach`/`sens_*`.
  - Desktop-only preserved across web save: `dcf.per_cf_tv_multiples`, `dcf.last_cf_mode`.
  - Derived caches stripped on web save (`wacc_value`, `ke_value`, `nwc_by_period`, `changes_in_nwc`, `interest_expense_by_period`, `fv_base`, `sum_pv_fcf`, …) and recomputed on load. int/float and None/float noise in derived rows is not a schema bug.
  - Migration path used (only 3 files, no library): open old web file on web → Save once → canonical. Old web file opened directly on desktop pre-fix showed `0,1,2,3,4,5` — closed without saving; core `_canonicalize_gpc_for_desktop()` also added for robustness.
  - Headless round-trip tests pass both directions (`test_roundtrip.py`; web→disk→web and desk→web→desk MATCH on all GPC slots, exclusions, per-basis, NWC %, CSRP, dashboard weights, DCF extras, GT).
- [X] **Desktop Projection parity (Sept 7).** `Ui/projection_module_page.py` patches 3A–3I + `main_window` collect/apply + label rename. Historical anchor `ebitda` → `adj_ebitda`; EBIT + Net Interest rows added; Taxes historical populated (was never written); `+Other Adjustments` now pre-tax plug with interest via `resolve_projection_waterfall(solve_other_adjustment=True)`; non-MS NI computed via waterfall, not typed; `other_adj`/`net_income`/`net_income_margin` persisted from `self._resolved`; projected interest callback passed from Debt Schedule. Display label `"EBITDA"` → `"Adjusted EBITDA (incl. SBC add-back)"` (internal `pd.ebitda` keys preserved).
- [X] **Desktop DCF parity (Sept 7).** Patches 1–11 + `sf("other_adj")` + sensitivity short-circuit. `_recalculate()` builds `hist/proj`, signed `net_interest_by_period` (hist: `income − |expense|`; proj: `−|debt cost|`), NWC changes, `other_adj_inputs`, TV inputs, `calculate_ppa()`, Ke-vs-WACC, then `build_dcf()`; renders via `_render_shared_dcf_rows()` / `_render_shared_terminal_values()`; bridge/residual/sensitivity read `_shared_calc`. `apply_state()` reordered to restore inputs before recalc; `bridge_other_adj` persisted; `get_residual_revenue()` full-precision; `main_window` refreshes DCF after NWC+Debt load. Old `_populate_*` chain bypassed (kept for rollback).
- [X] **GPC BEV subject-metrics fix (Sept 7).** `gpc_metrics.py`: `"TTM EBITDA"` + 3× `"NFY(+) Adjusted EBITDA"` line_key `"ebitda"` → `"adj_ebitda"`. Label strings unchanged (no session break). Fixes desktop GPC + web GPC + Dashboard together.
- [X] **Parity proof — `ADBE.json`, same file, Cached Data Only (Sept 7).**
  - Projection NFY/NFY+1/NFY+2: Rev 26,540/28,933/31,495; GP 23,728/25,867/28,158; Adj EBITDA 12,694/13,667/14,635; D&A 796/868/945; OA 345/376/409; SBC 2,123/2,025/1,417; EBIT 9,430/10,398/11,863; Net Interest −256/−275/−280; Other Adj −28/220/37; Taxes 1,921/2,172/2,440; NI 7,225/8,171/9,180; TTM Adj EBITDA 12,040 both.
  - DCF (Equity/FCFE/Ke=15.10%): Sum PV FCF 62,488; Disc Residual 37,878; FV Base 100,366; FV Low 90,131; FV High 114,276; sensitivity center = base (desktop was 100,370 pre-fix). BEV/FCFF/WACC also validated equal (OA row hidden, Ke→WACC switch correct).
  - GPC BEV Adobe Financial Data: 12,694 / 13,667 / 14,635 both surfaces, matching Projection + DCF.
- [ ] Desktop NWC/WACC port-back (optional cleanup — already tie; do not touch until dead-code removal window).
- [ ] Dash input-remount UX (Tab destroys focused cells). GitHub issue filed; `focus_keeper.js` was tried and discarded.
- [ ] Final multi-machine sync check (brother's Windows machine) — not re-verified against current `4_application/`.
- [ ] Remove bypassed desktop DCF `_populate_*` methods + old `_compute_fv_for_assumptions` body once parity bakes (currently fallback-only).

---

## 5. Known Issues / Technical Debt Log

| Item | Status |
|---|---|
| `cert.pem` / `key.pem` in `web/assets/` | Unused leftovers from abandoned HTTPS test. Candidate for deletion. |
| `web/components/navbar.py` | Empty file — `app.py` builds navbar inline. Dead scaffolding. |
| ~~GPC Weighting / column drift / DuplicateCallback / BEV↔Equity wipe~~ | **Resolved** earlier. |
| ~~EBITDA definition flip TTM→NFY~~ | **Resolved** in shared core (Step 7d). |
| ~~NWC / WACC / DCF / GT / Dashboard missing on web~~ | **Resolved** earlier stretch. |
| ~~GPC NWC Surplus placeholder~~ | **Resolved** — read-only from NWC page. |
| ~~GPC Equity indicated NA~~ | **Resolved** — `_num()` now strips `"x"`. |
| ~~Dashboard `dash.register_page()` crash~~ | **Resolved** — `web/lib/dcf_data.py`; never import pages from libs/callbacks. |
| ~~Web ↔ desktop save/load schema~~ | **Resolved Sept 7** — canonical desktop-shaped disk, web adapter both directions, headless round-trip MATCH. `0x/1x/2x` dict-key bug fixed via shape detection. |
| ~~GPC `0,1,2,3,4,5` on cross-open~~ | **Resolved Sept 7** — was web-dict keys misread as desktop-list values. Fixed in `web/lib/session_io.py` + `Canneberge/utils/session.py`. |
| ~~Desktop Projection drift (TTM EBITDA, missing EBIT/Interest/Taxes, wrong OA plug)~~ | **Resolved Sept 7** — now calls `resolve_projection_dollars()`; 5/5 match (TTM 12,040; EBIT; −256/−275/−280; Taxes; −28/220/37). |
| ~~Desktop Projection `other_adj` wiped on Save~~ | **Resolved Sept 7** — `_collect_data()` now fills `other_adj`/`net_income`/`margin` from `self._resolved`; `main_window` collect/apply persist it. |
| ~~DCF definition drift desktop vs web~~ | **Resolved Sept 7** — desktop now Adj EBITDA + full precision via `_shared_calc` + re-discount sensitivity. Old `_populate_*` bypassed. |
| ~~DCF `+Other Adjustments` blank on desktop~~ | **Resolved Sept 7** — desktop `sf("other_adj")` reads `ProjectionData.other_adj`; hist blank is correct (web shows `-`). |
| ~~DCF FV Low/High + sensitivity mismatch (center 100,370 vs base 100,366)~~ | **Resolved Sept 7** — both `_compute_fv_*` short-circuit to shared `fv_for_assumptions()`; Low 90,131 / High 114,276 match. |
| ~~GPC BEV Adobe data = conventional EBITDA~~ | **Resolved Sept 7** — shared `gpc_metrics.py` line_key → `adj_ebitda`; 12,694/13,667/14,635 both UIs. |
| Desktop DCF dead code | Old `_populate_*` (~20 methods) + old `_compute_fv_for_assumptions` body still present, bypassed. Remove after bake-in. |
| GPC `"TTM EBITDA"` label debt | Label kept for session compat; now resolves to `adj_ebitda`. Rename to `"TTM Adjusted EBITDA"` requires session migration — deferred. |
| Projection `pd.ebitda` key debt | Values are Adj EBITDA but key remains `"ebitda"` for session compat. Display label fixed. Same for DCF internal `"EBITDA"` row key. |
| `utils/session.py` recursive `deep_merge` | In place and correct; does extra deepcopy on 500KB cache. Fast shallow-merge version drafted but **not applied** — Cached Data Only loads in seconds; 8-min load was Full Web Refresh network (see below), not this code. Revisit only if cached loads lag. |
| Full Web Refresh 8-min load (Sept 7) | **Not a regression.** Stuck at `1/4 sources (25%)`, long pauses on StockAnalysis + MarketScreener, VS Code crashed mid-run. No traceback; finished OK. Cause: throttled/slow sources + loaded Chromebook. No code change. Use **Cached Data Only** for math audits. |
| Dash table remount on Tab | Recalc callbacks return a new `<table>` containing the inputs → cursor lost. Correct fix: structural render vs in-place calc cell updates. Issue filed on GitHub. |
| GPC Bridge — Equity mode | Not ported (web BEV-only). Desktop branch exists. |
| GPC Bridge — private cash | Stubbed to `None`. |
| GPC Company Name column | Can be blank; Home write path. |
| Non-Operating Assets on GPC Bridge | Still manual. |
| Projected interest income | Assumed zero by design (proj net interest = `−|expense|`). |
| Debt Schedule depth | No amortization / revolver / rate curves. |
| Reverse-DCF on desktop vs web | Both pre-existing; untouched by Sept 7 work. Not a save-format issue. |
| 3D Valuation Surface | Omitted on web; desktop hyperlink is unreachable tech debt. |
| Analytics page | Desktop only. Not on web. |
| Theme / scrollbar standardization | Not started — Step 9. |
| Dash `allow_duplicate` | Must pair with `prevent_initial_call=True` or `'initial_duplicate'`. Dynamic IDs need `allow_optional=True` until mounted (`dcf-residual-amortization`, NWC +/− buttons). |
| Home hydrate wildcard `ALL` | Returning a scalar `no_update` for `gpc-ticker-input` ALL is invalid; must return a list of 15 `no_update`s. |
| `compare_schemas.py` / `probe_shapes.py` / `test_roundtrip.py` / `TEST_*.json` | Sept 7 scaffolding in `4_application/` + `~/.canneberge/sessions/`. Keep until next parity check, then delete. Gold file is `ADBE.json`. |

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

### Sessions — one file, Cached Data Only for audits

```bash
ls ~/.canneberge/sessions/
# Gold file: ADBE.json — same file on both surfaces
# Sept 7 scaffolding: TEST_from_desktop.json, TEST_from_web.json, TEST_from_web_roundtrip_out.json
```

- Load with **Cached Data Only** when comparing math (reads frozen `source_data_results`, no network, seconds).
- **Full Web Refresh** re-scrapes ~11 tickers × 4 sources; 40s normal, 8+ min = throttled sources / loaded machine, not app code. Progress `Revenue: [...] · 1/4 sources` is the normal scraper dialog.
- Filenames with odd dashes: `mv -- *desktop*.json desktop.json` / `mv -- *web*.json web.json`, then compare.
- `ADBE.json` ≈ 493KB / ~18k lines with `indent=2` — normal. ~80% is `source_data_results` cache; typed inputs are only ~300–400 fields.

### Session-state keys now in use (`session-store`)

`projection_page_state` (incl. `other_adj`) · `gpc_page_state` (disk: `metric_selections`/`per_basis_state`/`excluded_rows`/`last_basis_mode`; memory on web: `metric_cols`/`basis_state`/`exclude_map`/`basis_mode`) · `debt_page_state` · `nwc_page_state` · `wacc_page_state` · `dcf_page_state` (incl. `per_cf_tv_multiples`/`last_cf_mode`, `bridge_other_adj`, `nols`, `sens_*`) · `gt_page_state` · `dashboard_page_state` (incl. `cost_values`, `debt_tic_stat`/`beta_stat`) · `private_is_data` / `private_bs_data`

On-disk canonical = desktop-shaped GPC + preserved extension keys. Web strips derived caches on save (`wacc_value`, `changes_in_nwc`, `surplus_deficit`, `fv_base`, `sum_pv_fcf`, `pv_residual`, …); both surfaces recompute on load and ignore unknown keys.

### Parity checks (Sept 7)

```bash
python test_roundtrip.py
# desktop file → web store → disk: every GPC slot/exclusion/per-basis + NWC/CSRP/dashboard/DCF/GT must MATCH

python -m py_compile Canneberge/Ui/dcf_page.py Canneberge/Ui/main_window.py Canneberge/Ui/projection_module_page.py Canneberge/Calculations/gpc_metrics.py
```

### Git Routine (End of Day)

```bash
git add .
git commit -m "Progress update: Phase 4 session adapter + projection/DCF/GPC parity"
git push
# Sept 7: committed + pushed to main (stage + push together — no staging without pushing)
```
### Message to the next chat (that means you)

Utilize the CLI Code Inspection or Precision Slicing methods in asking for files/code

#The Map (find where things live)
```bash
grep -n "^class \|^    def \|^def " path/to/file.py


#The Scalpel (Pull an exact line range)
```bash
sed -n '1842,1905p' Canneberge/Ui/filename.py

#The Sanity Check (check the file size first)
```bash
wc -l path/to/file.py
---

## 7. Next Steps (Prioritized)

1. ~~**Web ↔ desktop session adapter.**~~ **Done Sept 7.** Canonical desktop-shaped disk, bidirectional adapter, round-trip MATCH. Gold file `ADBE.json`.
2. ~~**Point desktop UIs at shared engines (Projection, DCF).**~~ **Done Sept 7.** Projection calls `resolve_projection_dollars()`; DCF calls `build_dcf()` + `fv_for_assumptions()`; GPC fixed via shared `gpc_metrics.py`. Remaining NWC/WACC port-back is optional (already tie) — schedule with dead-code removal, not as parity work.
3. ~~**DCF definition alignment.**~~ **Done Sept 7.** Adj EBITDA row; sensitivity re-discounts explicit FCFs; full precision via `_shared_calc`. Old desktop chain bypassed.
4. **Remove bypassed desktop DCF code** once parity bakes (next window): ~20 `_populate_*` methods, old `_compute_fv_for_assumptions` body, `_compute_fv_base_for` fallback. Keep `_shared_calc` render path only. Low risk, do not combine with math changes.
5. **Remaining GPC gaps:** Equity-mode bridge, private cash, Company Name write path, Non-Op Assets, `"TTM EBITDA"` label → `"TTM Adjusted EBITDA"` migration (needs session-string migration; line_key already correct).
6. **Dash input-remount UX** (GitHub issue): stop returning input-bearing tables from ordinary recalc callbacks. Projection Module first as the proof case. Unchanged.
7. **Step 9 — Theme + scroll standardization** now unblocked (surfaces share file format + engines). Extract `theme.py` roles to CSS custom properties; shared scroll-container helper.
8. **Housekeeping:** delete `cert.pem`/`key.pem`, empty `web/components/navbar.py`, Sept 7 scaffolding (`compare_schemas.py`, `probe_shapes.py`, `test_roundtrip.py`, `TEST_*.json`) after next check; decide fast shallow-merge `session.py` only if cached loads ever lag.
9. Analytics on web — not blocking.
10. Final multi-machine sync check (brother's Windows machine) — not re-verified against current `4_application/`.
```