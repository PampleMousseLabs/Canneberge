```markdown
# Phase 4: Canneberge Multi-Surface Application (Desktop & Web/PWA)

> **Current Status:** Web page migration is complete for Home, Source Data, Subject Financials, Projection Module, Debt Schedule, NWC, WACC, DCF (including Reverse-DCF), GT, GPC, and Dashboard. Shared calculation engines now exist for NWC, WACC, DCF, and GT. Remaining work is web↔desktop session-schema parity, pointing desktop UIs at the new `Canneberge/Calculations` modules, and Dash input-remount UX.
> **Active Branch:** `main`
> **Active Directory:** `4_application/`
> **Last Updated:** September 6, 2026

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
2. **Thin UI Adapters:** Neither the PyQt UI nor the Dash UI should contain business calculations. They import from `Canneberge.Calculations`, `Canneberge.Sources`, etc.
   * **Web is largely there:** `web/lib/subject_metrics.py`, `web/lib/nwc_data.py`, `web/lib/wacc_data.py`, `web/lib/dcf_data.py`, `web/lib/gt_data.py`, `web/lib/dashboard_data.py`, and the corresponding pages all delegate to `Canneberge.Calculations.*`.
   * **Desktop is not fully there yet:** `Canneberge/Ui/nwc_page.py`, `wacc_page.py`, `dcf_page.py`, and `gt_page.py` still contain local copies of math that now also lives in `Canneberge/Calculations/`. Port-back is an explicit next step — do not rip desktop math until that page matches the shared engine on the same session.
3. **No Dual Logic Maintenance:** If a formula or data source changes, it is edited **once** in `Canneberge/` and should update both UIs.
   * **Working rule:** any change that touches definitions, schema (`IS_LINES` / `BS_LINES`), or resolvers goes into `Canneberge/` first; `web/` only gets “make it render” edits.
4. **Headless page resolvers (web):** Dashboard and DCF must **never** `import web.pages.*` inside a callback. Importing a Dash page re-runs `dash.register_page()` and crashes. Cross-page reads go through `web/lib/*_data.py`.
5. **Local Network Privacy:** No public cloud servers, no port forwarding. Tailscale connects tablet/other devices to the Chromebook host over the home network only.

---

## 3. Directory Layout (`4_application/`) — corrected to match reality

**Correction from earlier drafts of this doc:** the planned `desktop/` folder move never happened, and won't. `3_code-migration/` is frozen and untouched going forward; its contents were copied into `4_application/Canneberge/` once, and that copy is now the only actively-edited version. The PyQt6 desktop app runs directly from `4_application/Canneberge/`, same package the web app's `Canneberge.Calculations` / `Sources` / etc. imports pull from. There is no separate `desktop/` wrapper layer.

```text
4_application/
│
├── Canneberge/                   # SHARED CORE ENGINE + PyQt6 desktop UI
│   ├── Calculations/
│   │   ├── subject_is_bs_calc.py # EBIT / EBITDA / Adj EBITDA / net_interest
│   │   ├── projection_resolve.py # resolve_projection_waterfall() — projected IS
│   │   ├── debt_schedule.py      # Tranche interest / ending debt / net borrowing
│   │   ├── nwc.py                # ✎ NEW — subject NWC, peer DFCFNWC, stats, bridge
│   │   ├── wacc.py               # ✎ NEW — betas, Ke, Kd, rounded WACC
│   │   ├── dcf.py                # ✎ NEW — waterfall, TV models, sensitivity re-discount
│   │   ├── gt.py                 # ✎ NEW — transaction multiples, indicated BEV, equity bridge
│   │   ├── gpc_metrics.py        # Forward metrics named Adjusted EBITDA + maps
│   │   ├── gpc_multiples.py      # Comp-side multiples
│   │   ├── ratio_catalogue.py    # Debt/TIC, historic structure, effective tax
│   │   ├── reverse_dcf.py        # Reverse-DCF solvers (Gordon / H-Model)
│   │   ├── valuation_surface.py  # Sensitivity / surface FV evaluator
│   │   └── chart_helper.py       # MethodRow bridge + football-field inputs
│   ├── Sources/                  # yfinance, FRED, StockAnalysis, MarketScreener
│   ├── Services/                 # Multi-source coordination
│   ├── Transforms/               # sa_key.py — SBC / other_amortization are CFS-sourced
│   ├── utils/
│   ├── Workers/
│   ├── Ui/                       # PyQt6 desktop pages (still contain local math; port-back pending)
│   ├── app_state.py              # IS_LINES / BS_LINES / dataclasses
│   └── config.py
│
├── web/                          # SURFACE B: Dash tablet/browser UI
│   ├── assets/
│   │   ├── manifest.json
│   │   └── custom.css            # Compact control strips
│   ├── lib/                      # Headless adapters — no Dash page imports
│   │   ├── subject_metrics.py    # Historical + projection metric resolver
│   │   ├── session_io.py
│   │   ├── nwc_data.py           # ✎ NEW — Residual revenue + NWC schedule
│   │   ├── wacc_data.py          # ✎ NEW — on-the-fly WACC / Ke
│   │   ├── dcf_data.py           # ✎ NEW — on-the-fly DCF (Dashboard-safe)
│   │   ├── gt_data.py            # ✎ NEW — GT adapter + formatters
│   │   ├── dashboard_data.py     # ✎ NEW — recon, bridge, football-field rows
│   │   └── ui_layout.py
│   ├── pages/
│   │   ├── home.py
│   │   ├── source_data.py
│   │   ├── subject_financials.py
│   │   ├── debt_schedule.py
│   │   ├── nwc.py                # ✎ NEW
│   │   ├── wacc.py               # ✎ NEW
│   │   ├── dcf.py                # ✎ NEW — was a placeholder
│   │   ├── gt.py                 # ✎ NEW
│   │   ├── gpc.py                # NWC surplus wired; range chart; Equity indicated parse fix
│   │   └── dashboard.py          # ✎ NEW — control dashboard, not a report
│   ├── components/
│   │   ├── projection_modal.py
│   │   ├── reverse_dcf_modal.py  # ✎ NEW
│   │   └── gt_range_chart.py     # ✎ NEW — Plotly candlestick reused by GT + GPC
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

### Phase 4.3: Page Migration (PyQt → Dash) — Substantially Complete

- [X] **Step 6: Home Page** — complete.
- [X] **Step 7: Real Source Data Pipeline** — complete. Wired to `Canneberge.Services.source_data_service`, per-source refresh, Refresh All, `DiskcacheManager`, live progress.
- [X] **Step 7b: Subject Financials** — complete. Shared `compute_is_calculated` / `IS_LINES`. Compact IS/BS toggles. Projected interest expense displayed negative in the **display layer only**; plumbing stays a positive cost so Projection Module EBIT math is unchanged. CFS SBC and Other Amortization feed Adjusted EBITDA.
- [X] **Step 7c: Projection Module** — complete. True statement waterfall: Adjusted EBITDA → Less D&A → Less Other Amort → Less SBC → EBIT → Net Interest → +Other Adjustments (pre-tax plug) → Taxes → Net Income → CapEx. Debt Schedule interest wired. Historical taxes = reported, not statutory × pretax.
- [X] **Step 7d: Income-Statement Definition Consolidation** — complete in shared core.
  - `EBIT = GP − OpEx`
  - `EBITDA (before SBC add-back) = EBIT + D&A + Other Amortization`
  - `Adjusted EBITDA = EBITDA + SBC`
  - Desktop Subject Financials picks this up automatically. Desktop Projection Module / DCF still have residual definition drift vs web (see Known Issues).
- [X] **Step 8: GPC Page** — complete for BEV workflow; remaining gaps listed under ⚠️.
  - Compact control strip; Home `basis_of_value` hydrates the starting toggle; local BEV/Equity still works.
  - `basis_state.BEV` / `basis_state.EQUITY` isolate `metric_cols`, selected multiples, and weights. Slice-aware persist (`ctx.triggered_id`) so a basis toggle cannot wipe the destination bucket.
  - `_safe_dict()` prevents crashes on legacy list-shaped session data.
  - Single shared `<table>` + `<colgroup>` for header/body alignment.
  - Forward subject metrics request `"adj_ebitda"` for NFY / NFY+1 / NFY+2.
  - **NWC Surplus/(Deficit)** is now read-only and sourced from `nwc_page_state["surplus_deficit"]` (no longer a manual placeholder).
  - **GPC Multiples Range Chart** pop-out (Plotly candlestick: Open=Q3, High=Max, Low=Min, Close=Q1). Reuses `web/components/gt_range_chart.py`.
  - Selected-multiple parser now strips `"x"` so Equity indicated values calculate (`"15.00x"` no longer becomes `0.0` / NA).
  - ⚠️ Bridge — BEV-mode formula chain only. Desktop Equity-mode branch (`eq_nctrl` → `eq_mkt_ctrl` → `eq_nonmkt_ctrl`) not ported.
  - ⚠️ Private-company cash path stubbed to `None`.
  - ⚠️ Non-Operating Assets, Net remains a manual placeholder.
  - ⚠️ Company Name column can still be blank if Home never wrote `gpc_company_names`.
- [X] **Step 11a: Debt Schedule** — complete. Shared `Calculations/debt_schedule.py`. Desktop-compatible `debt_page_state` plus cached `interest_expense_by_period` / `ending_debt_by_period` / `net_borrowing_by_period`. Fallback recompute from tranche rows if caches missing.
- [X] **Step 11b: NWC** — complete.
  - Shared `Canneberge/Calculations/nwc.py`; desktop page left untouched.
  - **Option A preserved:** Cash Treatment affects GPC peer NWC only. Subject NWC is always selected CA − selected CL.
  - Local Historical Years; global Projection Years (synced with Home).
  - TTM is a real column so NFY ΔNWC = NFY NWC − TTM NWC.
  - Residual column exists; Residual Revenue = final projected revenue × (1 + DCF LTGR) via `dcf.residual_revenue()` so DCF can consume `changes_in_nwc["Residual"]` without a circular page import.
  - Turnover Ratios basis blanks projected NWC (no projected BS).
  - GPC peer table, stats, Selected %, Normalized / Actual / Surplus/(Deficit), combo chart.
  - State compatible with desktop `collect_state()` plus web caches (`changes_in_nwc`, `surplus_deficit`, …).
- [X] **Step 11d: WACC** — complete.
  - Shared `Canneberge/Calculations/wacc.py`; desktop page left untouched.
  - Comp table, stats, Selected Debt%TIC / Tax (read-only Home rate) / Re-Levered Beta.
  - MCAPM Ke, FRED pretax Kd, after-tax Kd, We/Wd, WACC **rounded to 4 decimals** (2 dp as a percent) — that rounded value is what DCF consumes.
  - Preserved: magnitude percent parse (`5` → 5%, `0.5` → 50%); book vs market Debt/TIC by Capital Structure dropdown; Ke requires all four terms (blank Size Premium → NA, not 0).
  - `web/lib/wacc_data.py` is page-independent so DCF/Dashboard never import `web.pages.wacc`.
- [X] **Step 10: DCF Page** — complete (was a placeholder).
  - Shared `Canneberge/Calculations/dcf.py` + `web/lib/dcf_data.py` (Dashboard-safe; no `web.pages.dcf` import).
  - 25-row waterfall, no TTM column, Residual column, four TV models (Gordon / EBITDA Multiple / Revenue Multiple / H-Model), FV bridge, 5×5 sensitivity heatmap.
  - **Approved deviations from current desktop:**
    - EBITDA row is **Adjusted EBITDA** (matches Projection Module, MarketScreener, GPC forward).
    - Full precision (desktop rounds via label re-parse).
    - Sensitivity **re-discounts explicit-period FCFs** at the column rate (desktop held that sum fixed — heatmap was lopsided).
  - FCFE shows Net Interest and Projection Module **+Other Adjustments** so EBT − SBC + OA − Taxes foots to Net Income. Those rows hidden in FCFF.
  - FCF `Less: Other Adjustments` remains the cash-flow add-on (acquisitions / user plug), distinct from the P&L OA row.
  - Home Basis of Value overrides Cash Flows to (Equity → FCFE, BEV → FCFF).
  - Reverse-DCF modal (`web/components/reverse_dcf_modal.py`): ticker universe = subject + GPCs; each ticker’s **own observed beta** × WACC ERP; FCFE bridge; Gordon implied LTGR; H-Model solver; combo / H-bar / indexed-range charts.
  - 3D Valuation Surface omitted (desktop hyperlink is dead tech debt).
- [X] **Step 11c: GT Page** — complete.
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

### Phase 4.4: Hardening & Parity Check — In Progress

- [X] Web pages listed above persist through `dcc.Store` / `session-store`.
- [ ] **Web ↔ desktop session JSON is not equivalent.** Saving on one surface and opening on the other resets GPC (and likely GT/WACC/DCF) to defaults. See §7 item 1.
- [ ] Desktop UIs still duplicate math now living in `Canneberge/Calculations/{nwc,wacc,dcf,gt}.py`.
- [ ] Dash input-remount UX (Tab destroys focused cells). GitHub issue filed; `focus_keeper.js` was tried and discarded.
- [ ] Final multi-machine sync check (brother's Windows machine) — not re-verified against current `4_application/`.

---

## 5. Known Issues / Technical Debt Log

| Item | Status |
|---|---|
| `cert.pem` / `key.pem` in `web/assets/` | Unused leftovers from abandoned HTTPS test. Candidate for deletion. |
| `web/components/navbar.py` | Empty file — `app.py` builds navbar inline. Dead scaffolding. |
| ~~GPC Weighting / column drift / DuplicateCallback / BEV↔Equity wipe~~ | **Resolved** earlier. |
| ~~EBITDA definition flip TTM→NFY~~ | **Resolved** in shared core (Step 7d). |
| ~~NWC / WACC / DCF / GT / Dashboard missing on web~~ | **Resolved** this stretch. |
| ~~GPC NWC Surplus placeholder~~ | **Resolved** — read-only from NWC page. |
| ~~GPC Equity indicated NA~~ | **Resolved** — `_num()` now strips `"x"`. |
| ~~Dashboard `dash.register_page()` crash~~ | **Resolved** — `web/lib/dcf_data.py`; never import pages from libs/callbacks. |
| **Web ↔ desktop save/load schema** | **Open — next.** GPC: desktop lists (`metric_selections`, `selected_low`) vs web dicts (`metric_cols` keyed `"0"`); `per_basis_state` vs `basis_state`; `excluded_rows` vs `exclude_map`. Same class of mismatch likely on GT/WACC/DCF/Dashboard. Canonical format TBD; load-time adapter both directions. |
| Desktop UI still has local math | `nwc_page.py`, `wacc_page.py`, `dcf_page.py`, `gt_page.py`, `projection_module_page.py` not yet importing the new Calculation modules. Port only after numeric gold-standard match. |
| DCF definition drift desktop vs web | Web: Adj EBITDA row; full precision; sensitivity re-discounts explicit FCFs. Desktop: mixed EBITDA sourcing; label-rounded intermediates; sensitivity held explicit PV sum fixed. Conscious alignment required — not a silent import side effect. |
| Dash table remount on Tab | Recalc callbacks return a new `<table>` containing the inputs → cursor lost. Correct fix: structural render vs in-place calc cell updates. Issue filed on GitHub. |
| GPC Bridge — Equity mode | Not ported. |
| GPC Bridge — private cash | Stubbed to `None`. |
| GPC Company Name column | Can be blank; Home write path. |
| Non-Operating Assets on GPC Bridge | Still manual. |
| Projected interest income | Assumed zero by design. |
| Debt Schedule depth | No amortization / revolver / rate curves. |
| Reverse-DCF on desktop vs web | Web modal complete; desktop dialog already existed. Not a save-format issue. |
| 3D Valuation Surface | Omitted on web; desktop hyperlink is unreachable tech debt. |
| Analytics page | Desktop only. Not on web. |
| Theme / scrollbar standardization | Not started — Step 9. |
| Dash `allow_duplicate` | Must pair with `prevent_initial_call=True` or `'initial_duplicate'`. Dynamic IDs need `allow_optional=True` until mounted (`dcf-residual-amortization`, NWC +/− buttons). |
| Home hydrate wildcard `ALL` | Returning a scalar `no_update` for `gpc-ticker-input` ALL is invalid; must return a list of 15 `no_update`s. |

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

### Session-state keys now in use (`session-store`)

`projection_page_state` · `gpc_page_state` (incl. `basis_state.BEV/EQUITY`) · `debt_page_state` · `nwc_page_state` · `wacc_page_state` · `dcf_page_state` (incl. `reverse_dcf_state`) · `gt_page_state` · `dashboard_page_state` · `private_is_data` / `private_bs_data`

Web writes extra cached outputs (`wacc_value`, `changes_in_nwc`, `surplus_deficit`, `fv_base`, …). Desktop should ignore unknown keys. Desktop-shaped keys that web does not read on load are the actual round-trip bug.

### Git Routine (End of Day)

```bash
git add .
git commit -m "Progress update: Phase 4 web NWC/WACC/DCF/GT/Dashboard"
git push
```

---

## 7. Next Steps (Prioritized)

1. **Web ↔ desktop session adapter.** Dump one JSON from web and one from desktop on the same deal. Diff `gpc_page_state`, `gt_page_state`, `wacc_page_state`, `projection_page_state`, `nwc_page_state`, `dcf_page_state`, `dashboard_page_state`. Implement load-time mapping both directions. Prefer desktop list-shaped GPC as the on-disk canonical format (existing sessions). Prove GPC multiples survive web→desktop and desktop→web before anything else.
2. **Point desktop UIs at shared engines** — one page at a time (GT or WACC first; DCF last). Do not delete desktop math until that page ties out on the same session.
3. **DCF definition alignment (conscious desktop change):** Adj EBITDA row; whether sensitivity re-discounts explicit FCFs; intermediate rounding.
4. **Dash input-remount UX** (GitHub issue): stop returning input-bearing tables from ordinary recalc callbacks. Projection Module first as the proof case.
5. **Remaining GPC gaps:** Equity-mode bridge, private cash, Company Name, Non-Op Assets.
6. **Step 9 — Theme + scroll standardization** once the two surfaces share a file format.
7. Analytics on web — not blocking.
```