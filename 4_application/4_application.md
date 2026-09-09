# Phase 4: Canneberge Multi-Surface Application (Desktop & Web/PWA)

> **Current Status:** One-file workflow achieved. Same `~/.canneberge/sessions/*.json` opens on both surfaces. Session-schema adapter complete (desktop-canonical on disk, web translation in memory). Desktop Projection Module now calls shared `resolve_projection_dollars()` — 5/5 match. Desktop DCF now calls shared `build_dcf()` + `fv_for_assumptions()` — grid, TV, bridge, sensitivity match on both Equity/FCFE/Ke and BEV/FCFF/WACC. Shared `gpc_metrics.py` line_key fix repairs desktop GPC + web GPC + Dashboard at once. **Sept 8: shared `value_bridge.py` engine replaces `chart_helper.compute_bridge()` for Dashboard reconciliation — natural-level (DCF/GT controlling, GPC minority) → target-level (Controlling/Minority toggle) conversion, CP↔DLOC last-edit-wins, Non-Op Assets and CP/DLOC now Dashboard-owned on desktop. Web Dashboard + web GPC bridge wired to the new engine; desktop Dashboard + desktop GPC wired to the new engine. Web GPC input boxes and web NWC warning still pending.** Remaining: NWC/WACC desktop port-back (optional — inputs already tie), dead `_populate_*` removal, Dash input-remount UX, Theme, web GPC/NWC display cleanup for #22.
> **Active Branch:** `main`
> **Active Directory:** `4_application/`
> **Last Updated:** September 8, 2026

---

## 1. Project Overview & North Star

**Project Canneberge** is a Python-based financial valuation workstation (GPC multiples, DCF modeling, Debt Schedules, FRED/StockAnalysis/yfinance data aggregators, and WACC analysis).

* **Phase 1 & 2 (Frozen):** Excel prototype and model refinement. Excel is stale relative to current StockAnalysis page structure — not maintained as a live cross-check anymore.
* **Phase 3 (Frozen):** Python ETL migration & complete PyQt6 desktop application. **No longer developed as a separate codebase** — see Directory Layout correction below.
* **Phase 4 (Active):** Productized multi-surface deployment.
  * **Surface A (Desktop):** PyQt6 application, still run directly out of `4_application/Canneberge/`.
  * **Surface B (Tablet / Web):** Dash-based app, hosted on a Chromebook (`0.0.0.0:8050`) and accessed from tablet/other browsers over Tailscale on the home network. HTTPS was tested and scrapped — plain HTTP over Tailscale works fine for this use case and is what's actually running.
  * **Sept 7 rule:** one canonical file per deal in `~/.canneberge/sessions/` (e.g. `Adobe,_Inc..json`). No `*_desktop.json` / `*_web.json` pair maintenance. Web converts on load/save; desktop merges on save to preserve web-only keys.

---

## 2. Core Architectural Principles

1. **Single Source of Truth (Core):** All business logic, valuation math, scrapers, and transforms live strictly in `Canneberge/`.
2. **Thin UI Adapters:** Neither the PyQt UI nor the Dash UI should contain business calculations. They import from `Canneberge.Calculations`, `Canneberge.Sources`, etc.
   * **Web is there:** `web/lib/subject_metrics.py`, `web/lib/nwc_data.py`, `web/lib/wacc_data.py`, `web/lib/dcf_data.py`, `web/lib/gt_data.py`, `web/lib/dashboard_data.py`, and the corresponding pages all delegate to `Canneberge.Calculations.*`.
   * **Desktop is there for Projection + DCF (Sept 7) and Dashboard/GPC bridge (Sept 8):** `Ui/projection_module_page.py` harvests widgets then calls `resolve_projection_dollars()`; `Ui/dcf_page.py` collects inputs then calls `build_dcf()` / `fv_for_assumptions()` and renders `self._shared_calc`; `Ui/dashboard_page.py` and `Ui/gpc_page.py` now call `value_bridge.run_bridge()` / `value_for()` instead of local BEV round-trip math. Old `_populate_*` DCF methods and the old GPC IC-round-trip bridge are bypassed but not deleted (rollback safety).
   * **Desktop still local but tying out:** `Ui/nwc_page.py`, `wacc_page.py` still contain local math; inputs match and outputs tie on `Adobe,_Inc..json`, so port-back is optional cleanup, not a parity blocker. `Ui/gt_page.py` was already byte-identical to web (`gt_page_state` had zero diff) — no port needed.
3. **No Dual Logic Maintenance:** If a formula or data source changes, it is edited **once** in `Canneberge/` and should update both UIs.
   * **Working rule:** any change that touches definitions, schema (`IS_LINES` / `BS_LINES`), or resolvers goes into `Canneberge/` first; `web/` only gets “make it render” edits.
   * **Sept 7 proof:** one `gpc_metrics.py` line_key fix (`ebitda` → `adj_ebitda`) repaired desktop GPC, web GPC, and Dashboard simultaneously.
   * **Sept 8 proof:** `value_bridge.py` is the single conversion engine consumed by `web/lib/dashboard_data.py`, `web/pages/gpc.py`, `Canneberge/Ui/dashboard_page.py`, and `Canneberge/Ui/gpc_page.py` — a bridge formula edited once updates all four call sites.
4. **Headless page resolvers (web):** Dashboard and DCF must **never** `import web.pages.*` inside a callback. Importing a Dash page re-runs `dash.register_page()` and crashes. Cross-page reads go through `web/lib/*_data.py`.
5. **Local Network Privacy:** No public cloud servers, no port forwarding. Tailscale connects tablet/other devices to the Chromebook host over the home network only.
6. **Canonical session (Sept 7):** On-disk format is desktop-shaped (lists, 7-slot GPC, 15-row exclusions, `x`/`%` suffixes). Web translates to dicts/clean numbers in memory and back on save. Both surfaces preserve unknown extension keys. Derived caches (`wacc_value`, `changes_in_nwc`, `fv_base`, …) are stripped on save and recomputed on load.
7. **Value level vs. display basis are orthogonal (Sept 8).** Every valuation method has a **natural level** (DCF/GT = controlling, GPC = minority) and every method must be shown at the Dashboard's **target level** (Controlling | Minority) *and* a **display basis** (BEV | Equity | $/Share). These are two independent axes — the bridge engine adjusts only the methods whose natural level differs from the target. Observed market price/cap/EV is **never** level-adjusted; it is what the market actually shows.

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
│   │   ├── value_bridge.py       # ✎ NEW Sept 8 — natural-level → target-level BEV↔Equity↔Controlling↔Minority engine; CP↔DLOC inverse math; replaces chart_helper.compute_bridge() for Dashboard/GPC. Tested: CP↔DLOC round-trip exact, CP=0 identity, BEV_ctrl−BEV_min==CP×Equity_min, Equity mode excludes gross cash, DCF/GT DLOC-once.
│   │   └── chart_helper.py       # MethodRow / weighted_conclusion retained (football-field + weighting); compute_bridge() superseded by value_bridge.run_bridge()
│   ├── Sources/                  # yfinance, FRED, StockAnalysis, MarketScreener
│   ├── Services/                 # Multi-source coordination
│   ├── Transforms/               # sa_key.py — SBC / other_amortization are CFS-sourced
│   ├── utils/
│   │   └── session.py            # ✎ Sept 7 — deep-merge save + _canonicalize_gpc_for_desktop() on load
│   ├── Workers/
│   ├── Ui/                       # PyQt6 desktop pages
│   │   ├── projection_module_page.py # ✎ Sept 7 — thin: calls resolve_projection_dollars(), EBIT/Net Interest rows added
│   │   ├── dcf_page.py           # ✎ Sept 7 — thin renderer: calls build_dcf(), _shared_calc, +Other Adjustments row
│   │   ├── gpc_page.py           # ✎ Sept 8 — CP/DLOC/Non-Op inputs now read-only mirrors of Dashboard; bridge section rebuilt as generic label/low/high slots rendered from value_bridge.run_bridge()["lines"]; old IC round-trip math removed
│   │   ├── dashboard_page.py     # ✎ Sept 8 — DLOC now editable (was derived-only label); Level combo (Controlling/Minority) added; Non-Op Assets input added (Dashboard-owned); _collect_bridge_inputs/_collect_method_rows/_single_bridged_pair/recompute_reconciliation rewritten around value_bridge.run_bridge()/value_for()
│   │   └── main_window.py        # ✎ Sept 7 — projection other_adj collect/apply, interest callbacks, DCF refresh order. ✎ Sept 8 — GPCPage wired to _get_dashboard_bridge_values / _get_nwc_surplus_deficit callbacks; dashboard_page_state collect/apply extended with dloc/value_level/non_op/last_edited_discount
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
│   │   ├── dashboard_data.py     # ✎ Sept 8 — rewritten around value_bridge.run_bridge()/value_for(); dashboard_state_from_session() now owns control_premium/dloc/last_edited_discount/value_level/non_op; _bridge_inputs() supplies preferred_stock/minority_interest; _observed_on_basis() never level-adjusts
│   │   └── ui_layout.py
│   ├── pages/
│   │   ├── home.py
│   │   ├── source_data.py
│   │   ├── subject_financials.py
│   │   ├── debt_schedule.py
│   │   ├── nwc.py                # ⚠ warning-line patch pending (Sept 8) — cash double-count vs. bridge
│   │   ├── wacc.py
│   │   ├── dcf.py                # 26-row waterfall (incl. +Other Adjustments in FCFE)
│   │   ├── gt.py
│   │   ├── gpc.py                # ✎ Sept 8 — bridge block rewritten around value_bridge.run_bridge(); ⚠ CP/DLOC/Non-Op/NWC input boxes still editable on this page, not yet converted to read-only Dashboard mirrors (desktop already is)
│   │   └── dashboard.py          # ✎ Sept 8 — dash-dloc-input / dash-level / dash-non-op controls added; hydrate_dashboard() outputs extended (19→22); sync_cp_dloc() last-edit-wins callback added; persist_dashboard() tail extended
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
- [X] **Step 8: GPC Page** — complete for BEV workflow; **Sept 7 BEV subject-metrics fix** (shared `gpc_metrics.py` line_key); **Sept 8 bridge rewrite** (both surfaces now call `value_bridge.run_bridge()`). Remaining gaps listed under ⚠️.
  - Compact control strip; Home `basis_of_value` hydrates the starting toggle; local BEV/Equity still works.
  - `basis_state.BEV` / `basis_state.EQUITY` isolate `metric_cols`, selected multiples, and weights. Slice-aware persist (`ctx.triggered_id`) so a basis toggle cannot wipe the destination bucket.
  - `_safe_dict()` prevents crashes on legacy list-shaped session data.
  - Single shared `<table>` + `<colgroup>` for header/body alignment.
  - Forward subject metrics resolve `"adj_ebitda"` for NFY / NFY+1 / NFY+2 on **both** UIs (was web-only; desktop fixed via shared file).
  - **NWC Surplus/(Deficit)** is now read-only and sourced from `nwc_page_state["surplus_deficit"]` (no longer a manual placeholder).
  - **GPC Multiples Range Chart** pop-out (Plotly candlestick: Open=Q3, High=Max, Low=Min, Close=Q1). Reuses `web/components/gt_range_chart.py`.
  - Selected-multiple parser now strips `"x"` so Equity indicated values calculate (`"15.00x"` no longer becomes `0.0` / NA).
  - **Sept 8 — Bridge fully rewritten (#22).** Desktop `_build_bridge_section` now renders generic label/low/high slots populated from `value_bridge.run_bridge()["lines"]`; the old IC-round-trip (`ic_nctrl → ×(1+CP) → ic_ctrl → −cash/nwc/non_op → bev_ctrl`) math is gone. Equity mode: `Equity(min) + NWC + Non-Op = Adj Equity(min) → ×(1+CP) = Equity(ctrl)`, gross cash deliberately excluded. BEV mode: `BEV(min) − Debt − Pfd − NCI + Cash + NWC + Non-Op = Equity(min) → ×(1+CP) = Equity(ctrl) → +Debt+Pfd+NCI−Cash−NWC−NonOp = BEV(ctrl)`.
  - **Sept 8 — CP/DLOC/Non-Op ownership moved to Dashboard.** Desktop `control_premium_input`/`dloc_input`/`nwc_input`/`non_op_assets_input` are now read-only mirrors (`_lock_dashboard_owned_inputs()`), sourced via `_get_dashboard_bridge_values_callback` and `_get_nwc_surplus_callback` from `MainWindow`. ⚠️ Web GPC still has these as live editable inputs — parity gap, see Known Issues.
  - ⚠️ Private-company cash path stubbed to `None`.
  - ⚠️ Company Name column can still be blank if Home never wrote `gpc_company_names`.
  - ⚠️ `"TTM EBITDA"` label text preserved for session compat but now resolves to `adj_ebitda` under the hood (label debt — see Known Issues).
- [X] **Step 11a: Debt Schedule** — complete. Shared `Calculations/debt_schedule.py`. Desktop-compatible `debt_page_state` plus cached `interest_expense_by_period` / `ending_debt_by_period` / `net_borrowing_by_period`. Fallback recompute from tranche rows if caches missing.
- [X] **Step 11b: NWC** — complete for calculation; **Sept 8 — cash double-count warning pending** (see Known Issues / Next Steps).
  - Shared `Canneberge/Calculations/nwc.py`; desktop page left untouched (ties out, port optional).
  - **Option A preserved:** Cash Treatment affects GPC peer NWC only. Subject NWC is always selected CA − selected CL. Negative NWC preserved (`-4.2%` stays negative; adapter only adds/strips `%`).
  - Local Historical Years; global Projection Years (synced with Home).
  - TTM is a real column so NFY ΔNWC = NFY NWC − TTM NWC.
  - Residual column exists; Residual Revenue = final projected revenue × (1 + DCF LTGR) via `dcf.residual_revenue()` so DCF can consume `changes_in_nwc["Residual"]` without a circular page import.
  - Turnover Ratios basis blanks projected NWC (no projected BS).
  - GPC peer table, stats, Selected %, Normalized / Actual / Surplus/(Deficit), combo chart.
  - State compatible with desktop `collect_state()` plus web caches (`changes_in_nwc`, `surplus_deficit`, …).
  - **Sept 8 decision:** NWC page stays fully user-driven — no forced selector changes. A red warning line is being added instead (desktop patch written; web pending) when `cash`/`st_investments`/`trading_asset_securities` are selected in `ca_selections` or `cash_treatment == "Including Cash"`, since the value bridge always adds Cash separately and this would double-count. User explicitly wants to keep seeing cash-inclusive NWC for trend/peer comparison purposes — this is a visibility warning, not a behavior change.
- [X] **Step 11d: WACC** — complete.
  - Shared `Canneberge/Calculations/wacc.py`; desktop page left untouched (ties out, port optional).
  - Comp table, stats, Selected Debt%TIC / Tax (read-only Home rate) / Re-Levered Beta.
  - MCAPM Ke, FRED pretax Kd, after-tax Kd, We/Wd, WACC **rounded to 4 decimals** (2 dp as a percent) — that rounded value is what DCF consumes.
  - Preserved: magnitude percent parse (`5` → 5%, `0.5` → 50%); book vs market Debt/TIC by Capital Structure dropdown; Ke requires all four terms (blank Size Premium → NA, not 0).
  - `web/lib/wacc_data.py` is page-independent so DCF/Dashboard never import `web.pages.wacc`.
  - **Open question raised Sept 8 by user, not yet actioned:** now that Dashboard sits on the correct value level, CSRP can potentially be *implied* by back-solving against DCF/reverse-DCF outputs (same family as implied LTGR / implied STGR from Reverse-DCF), turning CSRP into a peer-comparable metric rather than a pure judgment input. Flagged as an Analytics idea (see §5/#15), not a WACC page change.
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
  - **Sept 8 note:** DCF's *natural level* is now formally defined as controlling for both FCFF and FCFE (see §2 item 7). The DCF page itself still only displays its own controlling-basis output; showing the Dashboard-selected target level (e.g. minority after DLOC) directly on the DCF/GT pages is deferred — tracked in Next Steps.
- [X] **Step 11c: GT Page** — complete for calculation; **Sept 8 note:** GT's natural level (controlling) is now explicit in the shared engine, and Dashboard applies DLOC to GT when target = Minority via `value_bridge.run_bridge(natural_level="controlling", ...)`. GT page itself unchanged this session.
  - Shared `Canneberge/Calculations/gt.py` + `web/lib/gt_data.py`.
  - GPC-style layout: split header/body callbacks, sibling Statistics / Selected / Subject / Weighting tables, separate Bridge card.
  - Transactions owned by Home; analysis only on GT.
  - DLOC field is read-only; Dashboard Control Premium is source of truth (`DLOC = CP / (1 + CP)`, now bidirectional — see Step 12). Until Dashboard writes it, saved `gt_page_state.dloc` is used.
  - Range chart modal (Q3/Max/Min/Q1 candlestick).
- [X] **Step 12: Dashboard** — **Sept 8 major rework of Reconciliation/Bridge (#22).** No longer a naive weighted-BEV pass-through; now a proper natural-level → target-level valuation reconciliation.
  - Income Approach: WACC fields (Debt/TIC + Beta with Median/Custom stats, ERP, Size, CSRP, pretax series, WACC output) and DCF options (TV model, LTGR, multiple / H-Model fields, Dep % of CapEx).
  - Market Approach: GPC (up to 7) and GT (up to 3) metric / low / high / weight rows; How Many resets even weights.
  - **Reconciliation of Values — rebuilt Sept 8:**
    - **Control Premium** and **DLOC** are both now live, editable, last-edit-wins (`DLOC = CP/(1+CP)`, `CP = DLOC/(1-CP... )` inverse), backed by `Canneberge.Calculations.value_bridge.cp_to_dloc/dloc_to_cp`. Web: `dash-cp` / `dash-dloc-input` with a `sync_cp_dloc` callback. Desktop: `control_premium_input` / `dloc_input` with `_on_control_premium_edited` / `_on_dloc_edited`.
    - **New Level of Value toggle: Controlling | Minority** (`dash-level` web / `level_combo` desktop). Independent of Display Basis (BEV | Equity | $/Share).
    - **New Non-Operating Assets input**, now Dashboard-owned (`dash-non-op` web / `non_op_input` desktop) — previously a GPC-only placeholder.
    - DCF / GT (natural level = controlling) and GPC (natural level = minority) are each run through `value_bridge.run_bridge()` and displayed via `value_for(result, target_level, display_basis)` — previously GPC skipped the bridge entirely and DCF/GT used a since-corrected `apply_dloc` flag that double-counted the GPC-equity-mode adjustment on FCFE.
    - **Observed EV / Market Cap / Share Price is never level-adjusted** — `_observed_on_basis()` is a pure market observation (`price × shares`, optionally ± debt/preferred/NCI/cash for BEV display), independent of the CP/DLOC toggle. Acceptance test: CP = 0% should collapse Controlling ≡ Minority and, with correctly selected multiples, land the concluded FV at the observed price.
  - Cost Approach: layout + persisted inputs only (NAV not calculated).
  - Football-field chart (Plotly): one bar per method line, observed marker, concluded FV line. **Sept 8:** bars now move with the Level toggle (Controlling pushes GPC bars right of observed; Minority pulls DCF/GT bars left) — this is the intended visualization purpose of the Level toggle, not a bug.
  - Two-way last-edit-wins via **session-store** (`wacc_page_state`, `dcf_page_state`, `gpc_page_state`, `gt_page_state`, `dashboard_page_state`). Dash cannot bind live PyQt widgets across unmounted pages.
  - Illegal `import web.pages.dcf` inside callbacks was the blank-Dashboard crash (`dash.register_page() can't be called within a callback`). Fixed by `web/lib/dcf_data.py`.
  - **Sept 8 regression fixed same-day:** `hydrate_dashboard()`'s `Output("dash-cp", "value")` lacked `allow_duplicate=True`, conflicting with the new `sync_cp_dloc()` callback's duplicate output on the same ID — Dash silently failed to register callbacks, rendering the page with populated layout but zero live values and no error banner. Fixed by adding `allow_duplicate=True` + `prevent_initial_call='initial_duplicate'` and extending the early-return tuple length (19→22) to match the three new outputs (`dash-dloc-input`, `dash-level`, `dash-non-op`).
- [ ] **Step 9: Theme System** — not started. Web DARKLY ≈ desktop One Dark Pro, not Slate & Gold. Extract `theme.py` roles to CSS custom properties. Shared scroll-container helper still pending.

### Phase 4.4: Hardening & Parity Check — Substantially Complete

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
  - **Sept 8:** `dashboard_page_state` schema extended (`dloc`, `value_level`, `non_op`, `last_edited_discount`); `main_window.py` collect/apply updated to persist these on desktop. Web `dashboard_state_from_session()` normalizes/defaults the same keys. Not yet re-run through `test_roundtrip.py` after this session's changes — see Next Steps.
- [X] **Desktop Projection parity (Sept 7).** `Ui/projection_module_page.py` patches 3A–3I + `main_window` collect/apply + label rename. Historical anchor `ebitda` → `adj_ebitda`; EBIT + Net Interest rows added; Taxes historical populated (was never written); `+Other Adjustments` now pre-tax plug with interest via `resolve_projection_waterfall(solve_other_adjustment=True)`; non-MS NI computed via waterfall, not typed; `other_adj`/`net_income`/`net_income_margin` persisted from `self._resolved`; projected interest callback passed from Debt Schedule. Display label `"EBITDA"` → `"Adjusted EBITDA (incl. SBC add-back)"` (internal `pd.ebitda` keys preserved).
- [X] **Desktop DCF parity (Sept 7).** Patches 1–11 + `sf("other_adj")` + sensitivity short-circuit. `_recalculate()` builds `hist/proj`, signed `net_interest_by_period` (hist: `income − |expense|`; proj: `−|debt cost|`), NWC changes, `other_adj_inputs`, TV inputs, `calculate_ppa()`, Ke-vs-WACC, then `build_dcf()`; renders via `_render_shared_dcf_rows()` / `_render_shared_terminal_values()`; bridge/residual/sensitivity read `_shared_calc`. `apply_state()` reordered to restore inputs before recalc; `bridge_other_adj` persisted; `get_residual_revenue()` full-precision; `main_window` refreshes DCF after NWC+Debt load. Old `_populate_*` chain bypassed (kept for rollback).
- [X] **GPC BEV subject-metrics fix (Sept 7).** `gpc_metrics.py`: `"TTM EBITDA"` + 3× `"NFY(+) Adjusted EBITDA"` line_key `"ebitda"` → `"adj_ebitda"`. Label strings unchanged (no session break). Fixes desktop GPC + web GPC + Dashboard together.
- [X] **Parity proof — `Adobe,_Inc..json`, same file, Cached Data Only (Sept 7).**
  - Projection NFY/NFY+1/NFY+2: Rev 26,540/28,933/31,495; GP 23,728/25,867/28,158; Adj EBITDA 12,694/13,667/14,635; D&A 796/868/945; OA 345/376/409; SBC 2,123/2,025/1,417; EBIT 9,430/10,398/11,863; Net Interest −256/−275/−280; Other Adj −28/220/37; Taxes 1,921/2,172/2,440; NI 7,225/8,171/9,180; TTM Adj EBITDA 12,040 both.
  - DCF (Equity/FCFE/Ke=15.10%): Sum PV FCF 62,488; Disc Residual 37,878; FV Base 100,366; FV Low 90,131; FV High 114,276; sensitivity center = base (desktop was 100,370 pre-fix). BEV/FCFF/WACC also validated equal (OA row hidden, Ke→WACC switch correct).
  - GPC BEV Adobe Financial Data: 12,694 / 13,667 / 14,635 both surfaces, matching Projection + DCF.
- [X] **Shared valuation-level bridge engine built and unit-tested (Sept 8).** `Canneberge/Calculations/value_bridge.py` — headless test suite (5 assertions) passing: CP↔DLOC round-trip exact (0.24 → 0.193548 → 0.24); CP=0 collapses Controlling≡Minority identically; `BEV_ctrl − BEV_min == CP × Equity_min` (21,302.64 both sides on test fixture); Equity-mode cash toggle isolates gross-cash inclusion exactly (diff = 4,919.00 = input cash); DCF/GT controlling→minority DLOC applied exactly once (98,761 → 79,645.97 at DLOC 19.35%).
- [X] **`run_bridge()` corrected mid-session (Sept 8) before desktop port.** First implementation incorrectly applied GPC's minority-equity normalization (+NWC+Non-Op) to controlling-native DCF FCFE, which should pass through unchanged at the equity-controlling level. Rewrote `run_bridge()` to branch cleanly on `natural_level` (minority → GPC path with CP uplift; controlling → DCF/GT path with DLOC-down) before any UI wiring — avoided propagating the bug into both desktop files.
- [X] **Web Dashboard reconciliation rewired to `value_bridge` (Sept 8).** `web/lib/dashboard_data.py`: `dashboard_state_from_session()` now owns `control_premium`/`dloc`/`last_edited_discount`/`value_level`/`non_op` with inverse-sync defaulting; `_bridge_inputs()` supplies `preferred_stock`/`minority_interest` via `get_subject_metric_value`; `_observed_on_basis()` includes preferred/NCI in BEV observed EV, never grosses up for CP; `get_dashboard_results()` runs DCF/GPC/GT each through `run_bridge()` at their natural level and reads `value_for(result, target_level, basis)` for both the reconciliation pairs and the football-field rows.
- [X] **Web Dashboard UI wired (Sept 8).** New `dash-dloc-input` (replaces derived-only `dash-dloc` label, kept hidden for compat), `dash-level` (Controlling/Minority), `dash-non-op`. `sync_cp_dloc()` last-edit-wins callback. `render_dashboard_outputs()` and `persist_dashboard()` extended to read/write all four new fields plus `last_edited_discount`.
- [X] **Blank-Dashboard regression found and fixed same session (Sept 8).** Root cause: `hydrate_dashboard()` output `dash-cp` without `allow_duplicate`, colliding with new `sync_cp_dloc()`'s duplicate output on the same ID — Dash refused registration silently (page rendered, no values, no error). Fixed via `allow_duplicate=True` on the hydrate output + `prevent_initial_call='initial_duplicate'` + early-return tuple length 19→22.
- [X] **Headless proof — web Dashboard producing correct levelled numbers (Sept 8), `Adobe,_Inc..json`, Controlling / $/Share:** `DCF (243.69, 283.60)`, `GPC (312.87, 348.33)`, `GT (296.61, 366.13)`, `concluded 297.12`, `dloc 0.194`, `cp 0.24`, `10 football rows`. This is the first Dashboard output where GPC actually receives its Control Premium uplift and DCF/GT are correctly left at controlling — previously GPC's CP never reached reconciliation at all.
- [X] **Web GPC bridge rewritten around `value_bridge` (Sept 8).** `web/pages/gpc.py`: bridge block now builds a `BridgeInputs` from Dashboard state (`dashboard_state_from_session`) + `get_subject_debt`/`get_subject_metric_value` for preferred/NCI, calls `run_bridge(natural_level="minority", ...)`, and renders `bridge_result["lines"]` generically instead of the old fixed 12-row IC-round-trip table. Terminal row labeled `"... → Dashboard"` per spec.
- [X] **Desktop Dashboard rewritten around `value_bridge` (Sept 8).** `Canneberge/Ui/dashboard_page.py`: `dloc_input` now editable (was a derived-only `implied_dloc_label`, aliased for back-compat), `level_combo` (Controlling/Minority) and `non_op_input` added to the Reconciliation panel; `_on_control_premium_edited`/`_on_dloc_edited`/`_on_level_changed`/`_on_non_op_edited` handlers; `bridge_values()` / `target_level()` public accessors for GPC to consume; `_push_bridge_inputs_to_pages()` mirrors CP/DLOC/Non-Op onto GPC/GT read-only fields; `_collect_bridge_inputs()` now supplies `preferred_stock`/`minority_interest`; `_collect_method_rows()` and `_single_bridged_pair()` rewritten around `run_bridge()`/`value_for()`; `recompute_reconciliation()` uses the same; `_share_price_on_basis()` (observed marker) extended for preferred/NCI, still never CP-adjusted; `apply_bridge_state()` added for session load.
- [X] **Desktop GPC rewritten around `value_bridge` (Sept 8).** `Canneberge/Ui/gpc_page.py`: constructor takes `get_dashboard_bridge_values_callback` / `get_nwc_surplus_callback` (safe no-op before Dashboard exists, since GPC constructs first); `_build_bridge_section` replaced with 10 generic label/low/high slots (`BRIDGE_ROW_SLOTS`) + `_render_bridge_rows()`; CP/DLOC/NWC/Non-Op input widgets converted to read-only mirrors via `_lock_dashboard_owned_inputs()`; recalculation block replaced with `run_bridge(natural_level="minority", source_basis=...)` call, mirroring Dashboard-owned values back onto the read-only widgets for display continuity.
- [X] **`main_window.py` wiring for Sept 8 changes.** `GPCPage(...)` construction passes the two new callbacks; `_get_dashboard_bridge_values()` / `_get_nwc_surplus_deficit()` added (dashboard-not-yet-constructed-safe); dashboard-state collect adds `dloc`/`value_level`/`non_op`/`last_edited_discount`; dashboard-state apply calls new `dp.apply_bridge_state(state)`.
- [X] **NWC cash double-count warning — desktop patch written (Sept 8).** `Ui/nwc_page.py`: new `cash_bridge_warning` QLabel (red, bold, word-wrap) shown when `cash_treatment == "Including Cash"` or any of `cash`/`st_investments`/`trading_asset_securities` is a selected CA row; `_update_cash_bridge_warning()` called from the existing recalc path. Fires immediately on `Adobe,_Inc..json` (all three cash-like rows selected + Including Cash) — expected, confirms the warning logic is live. **Web equivalent not yet written.**
- [ ] **Web GPC CP/DLOC/Non-Op/NWC inputs still locally editable — parity gap with desktop.** Desktop converted these to read-only Dashboard mirrors same session; web page (`web/pages/gpc.py`) still has `gpc-control-premium-pct`, `gpc-dloc-pct`, `gpc-non-op-input`, `gpc-nwc-input` as live inputs whose values are now ignored by the calculation (bridge reads Dashboard state instead) but the boxes are still shown as editable, which will confuse a user into thinking they do something. Needs the same read-only-mirror treatment as desktop; not done this session.
- [ ] **Web NWC cash double-count warning not yet implemented** (desktop only, see above).
- [ ] **`test_roundtrip.py` not re-run since Sept 8 `dashboard_page_state` schema extension.** New keys (`dloc`, `value_level`, `non_op`, `last_edited_discount`) added to both surfaces' collect/apply and to `dashboard_state_from_session()`'s normalization, but the automated round-trip regression test predates this and should be re-run before the next session to confirm desktop↔web save/load still matches for the extended Dashboard state.
- [ ] Desktop NWC/WACC port-back (optional cleanup — already tie; do not touch until dead-code removal window).
- [ ] Dash input-remount UX (Tab destroys focused cells). GitHub issue filed; `focus_keeper.js` was tried and discarded.
- [ ] Final multi-machine sync check (brother's Windows machine) — not re-verified against current `4_application/`.
- [ ] Remove bypassed desktop DCF `_populate_*` methods + old `_compute_fv_for_assumptions` body once parity bakes (currently fallback-only).
- [ ] Remove bypassed desktop GPC old-bridge helper code (`bridge_computed_labels_low/high` dicts kept empty for compat, old `ic_nctrl`/`ic_ctrl`/`eq_mkt_nctrl`/etc. label keys no longer populated) once the generic-slot bridge bakes.
- [ ] **DCF / GT page-level display of Dashboard target level** — deferred. Currently DCF and GT pages always display their own natural (controlling) output; only the Dashboard reconciliation/football-field actually shows the target-level-adjusted number. Whether the DCF/GT pages themselves should also show a "this is what Dashboard concludes at Minority" line is an open design question, not yet scoped.

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
| ~~Dashboard GPC reconciliation skipped Control Premium (#22 root cause)~~ | **Resolved Sept 8** — `_gpc_block`/`_bridge_inputs` previously fed raw weighted `fmv_low/high` straight into `compute_bridge` with `apply_dloc=False`, so GPC's CP step never ran before hitting reconciliation. New `value_bridge.run_bridge(natural_level="minority", ...)` runs GPC through its full CP-uplift chain before Dashboard consumes it. |
| ~~GPC page's old IC-round-trip bridge applied CP to invested capital (still containing debt), not equity~~ | **Resolved Sept 8** — old `(BEV+Cash+NWC+NonOp)×(1+CP)` overstated by `CP × Debt`; new chain applies CP at the equity level per user-specified BEV/Equity chains, matching `BEV_ctrl − BEV_min == CP × Equity_min` identity (unit-tested). |
| ~~`run_bridge()` double-applied GPC-equity normalization to DCF FCFE~~ | **Resolved Sept 8, same session, before desktop port** — corrected to branch on `natural_level` before any UI wiring occurred; controlling-native equity (DCF FCFE) now passes through unchanged rather than receiving `+NWC+Non-Op`. |
| ~~Dashboard blank / no error after Sept 8 CP↔DLOC wiring~~ | **Resolved Sept 8** — `hydrate_dashboard()` missing `allow_duplicate=True` on `dash-cp` conflicted with new `sync_cp_dloc()` callback; Dash silently refused registration. Fixed with `allow_duplicate=True`, `prevent_initial_call='initial_duplicate'`, and early-return tuple length 19→22. |
| Desktop DCF dead code | Old `_populate_*` (~20 methods) + old `_compute_fv_for_assumptions` body still present, bypassed. Remove after bake-in. |
| Desktop GPC dead bridge code | `bridge_computed_labels_low/high`, old keyed label dicts (`ic_nctrl`, `ic_ctrl`, `eq_mkt_nctrl`, etc.) kept for compat but no longer populated by the generic-slot bridge. Remove after bake-in. |
| GPC `"TTM EBITDA"` label debt | Label kept for session compat; now resolves to `adj_ebitda`. Rename to `"TTM Adjusted EBITDA"` requires session migration — deferred. |
| Projection `pd.ebitda` key debt | Values are Adj EBITDA but key remains `"ebitda"` for session compat. Display label fixed. Same for DCF internal `"EBITDA"` row key. |
| **Web GPC CP/DLOC/Non-Op/NWC still locally editable** | **Open — parity gap.** Desktop converted these to read-only Dashboard mirrors Sept 8; web page still shows them as live inputs whose values the calculation now ignores (bridge reads Dashboard state). Misleading UI until fixed — see Next Steps #1. |
| **Web NWC cash double-count warning not implemented** | **Open.** Desktop patch (`cash_bridge_warning` QLabel) written and firing correctly on the test session; web equivalent not started. |
| `utils/session.py` recursive `deep_merge` | In place and correct; does extra deepcopy on 500KB cache. Fast shallow-merge version drafted but **not applied** — Cached Data Only loads in seconds; 8-min load was Full Web Refresh network (see below), not this code. Revisit only if cached loads lag. |
| Full Web Refresh 8-min load (Sept 7) | **Not a regression.** Stuck at `1/4 sources (25%)`, long pauses on StockAnalysis + MarketScreener, VS Code crashed mid-run. No traceback; finished OK. Cause: throttled/slow sources + loaded Chromebook. No code change. Use **Cached Data Only** for math audits. |
| **VS Code Source Control showing ~43 changed files (Sept 8)** | **Investigate before committing.** Only ~5 files were intentionally edited this session (`dashboard_page.py`, `gpc_page.py`, `main_window.py`, `nwc_page.py`, `value_bridge.py` (new)). Suspected cause: format-on-save / line-ending (CRLF↔LF) normalization touching untouched files after a VS Code crash/reload, possibly triggered by a dismissed "convert" prompt. Diagnostic: `git diff --stat` vs `git diff --ignore-all-space --stat` — if a file's diff disappears under the space-ignoring flag, it's whitespace-only, not a real change. Recommend `"editor.formatOnSave": false` / `"files.eol": "\n"` workspace settings going forward, and reviewing/splitting the commit so whitespace-only churn doesn't bury the real diff. |
| Dash table remount on Tab | Recalc callbacks return a new `<table>` containing the inputs → cursor lost. Correct fix: structural render vs in-place calc cell updates. Issue filed on GitHub. |
| GPC Bridge — private cash | Stubbed to `None` (both surfaces). |
| GPC Company Name column | Can be blank; Home write path. |
| Projected interest income | Assumed zero by design (proj net interest = `−|expense|`). |
| Debt Schedule depth | No amortization / revolver / rate curves. |
| Reverse-DCF on desktop vs web | Both pre-existing; untouched by Sept 7–8 work. Not a save-format issue. |
| 3D Valuation Surface | Omitted on web; desktop hyperlink is unreachable tech debt. |
| Analytics page | Desktop only. Not on web. Idea backlog now includes **implied CSRP** (see §7 Analytics note below), historical subject-vs-peer multiple trend bands, PVGO-style mispriced-growth identification (scrapped once, reverse-DCF implied LTGR covers the same ground). |
| Theme / scrollbar standardization | Not started — Step 9. |
| Dash `allow_duplicate` | Must pair with `prevent_initial_call=True` or `'initial_duplicate'`. Dynamic IDs need `allow_optional=True` until mounted (`dcf-residual-amortization`, NWC +/− buttons). **Sept 8 real-world hit:** `dash-cp` output collision — see resolved-issues row above; this is the general rule that bug was an instance of. |
| Home hydrate wildcard `ALL` | Returning a scalar `no_update` for `gpc-ticker-input` ALL is invalid; must return a list of 15 `no_update`s. |
| `compare_schemas.py` / `probe_shapes.py` / `test_roundtrip.py` / `TEST_*.json` | Sept 7 scaffolding in `4_application/` + `~/.canneberge/sessions/`. Keep until next parity check (needs to also cover Sept 8 Dashboard schema additions), then delete. Gold file is `Adobe,_Inc..json`. |
| DCF / GT pages don't display Dashboard's target-level number | Both pages show their own natural-level (controlling) output only; Dashboard is the only place the Minority-adjusted number appears. Open design question, not yet scoped — see Roadmap. |
| International ticker support (GitHub #33) | Open research item, unrelated to Sept 7–8 work — compatibility matrix needed for yfinance/StockAnalysis/MarketScreener across Euronext/KRX-style suffixed tickers before any code changes. |

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
# Gold file: Adobe,_Inc..json — same file on both surfaces
# Sept 7 scaffolding: TEST_from_desktop.json, TEST_from_web.json, TEST_from_web_roundtrip_out.json
```

- Load with **Cached Data Only** when comparing math (reads frozen `source_data_results`, no network, seconds).
- **Full Web Refresh** re-scrapes ~11 tickers × 4 sources; 40s normal, 8+ min = throttled sources / loaded machine, not app code. Progress `Revenue: [...] · 1/4 sources` is the normal scraper dialog.
- Filenames with odd punctuation (commas, double dots, embedded spaces from company names): tab-complete or glob rather than retyping — `Path.glob("Adobe*.json")` in a script, or `ls` + copy/paste in the shell. Don't assume a filename from memory across a long session; confirm with `ls ~/.canneberge/sessions/` first.
- `Adobe,_Inc..json` ≈ 493KB / ~18k lines with `indent=2` — normal. ~80% is `source_data_results` cache; typed inputs are only ~300–400 fields.

### Session-state keys now in use (`session-store`)

`projection_page_state` (incl. `other_adj`) · `gpc_page_state` (disk: `metric_selections`/`per_basis_state`/`excluded_rows`/`last_basis_mode`; memory on web: `metric_cols`/`basis_state`/`exclude_map`/`basis_mode`) · `debt_page_state` · `nwc_page_state` · `wacc_page_state` · `dcf_page_state` (incl. `per_cf_tv_multiples`/`last_cf_mode`, `bridge_other_adj`, `nols`, `sens_*`) · `gt_page_state` · `dashboard_page_state` (incl. `cost_values`, `debt_tic_stat`/`beta_stat`, and **Sept 8:** `control_premium`/`dloc`/`last_edited_discount`/`value_level`/`non_op`) · `private_is_data` / `private_bs_data`

On-disk canonical = desktop-shaped GPC + preserved extension keys. Web strips derived caches on save (`wacc_value`, `changes_in_nwc`, `surplus_deficit`, `fv_base`, `sum_pv_fcf`, `pv_residual`, …); both surfaces recompute on load and ignore unknown keys.

### Parity checks

```bash
python test_roundtrip.py
# desktop file → web store → disk: every GPC slot/exclusion/per-basis + NWC/CSRP/dashboard/DCF/GT must MATCH
# ⚠ Not yet re-run since Sept 8 dashboard_page_state schema extension (dloc/value_level/non_op/last_edited_discount)

python -m py_compile Canneberge/Ui/dcf_page.py Canneberge/Ui/main_window.py Canneberge/Ui/projection_module_page.py Canneberge/Calculations/gpc_metrics.py Canneberge/Ui/dashboard_page.py Canneberge/Ui/gpc_page.py Canneberge/Ui/nwc_page.py Canneberge/Calculations/value_bridge.py
```

### Headless Dashboard check (no browser/Qt needed)

```bash
python - <<'PY'
import traceback
from pathlib import Path
from web.lib.session_io import load_session_to_stores
from web.lib.dashboard_data import get_dashboard_results

p = Path.home() / ".canneberge" / "sessions" / "Adobe,_Inc..json"
session_data, source_results, _ = load_session_to_stores(p)

try:
    res = get_dashboard_results(session_data, source_results)
    print("target_level:", res.get("target_level"))
    print("basis:", res.get("basis"))
    print("pairs:", res.get("pairs"))
    print("concluded:", res.get("concluded"))
    print("dloc:", res.get("dloc"), "cp:", res.get("control_premium"))
    print("football rows:", len(res.get("football") or []))
except Exception:
    traceback.print_exc()
PY
```

### Precision Slicing (for pulling code into chat without pasting whole files)

```bash
# The Map — find where things live
grep -n "^class \|^    def \|^def " path/to/file.py

# The Scalpel — pull an exact line range
sed -n '1842,1905p' Canneberge/Ui/filename.py

# The Sanity Check — file size before deciding cat vs. slice
wc -l path/to/file.py
```

### Git Routine (End of Day)

```bash
git status --short          # confirm what actually changed before staging
git diff --stat              # size sanity check
git diff --ignore-all-space --stat   # if a file's diff vanishes here, it's whitespace-only
git add .
git commit -m "Progress update: Phase 4 value_bridge engine + Dashboard/GPC reconciliation rewrite"
git push
# Stage and push together — no staging without pushing.
```

---

## 7. Next Steps (Prioritized)

1. **Web GPC CP/DLOC/Non-Op/NWC inputs → read-only Dashboard mirrors.** Desktop already did this Sept 8 (`_lock_dashboard_owned_inputs()`); web page (`web/pages/gpc.py`) still renders `gpc-control-premium-pct` / `gpc-dloc-pct` / `gpc-non-op-input` / `gpc-nwc-input` as live editable inputs even though the calculation now sources these from Dashboard state. Convert to disabled/read-only display text sourced from `dashboard_state_from_session()`. Needs a layout slice of `web/pages/gpc.py` around the control strip (~lines 180–310).
2. **Web NWC cash double-count warning.** Port the desktop `cash_bridge_warning` pattern (`Ui/nwc_page.py`) to `web/pages/nwc.py` — fires when `cash_treatment == "Including Cash"` or `cash`/`st_investments`/`trading_asset_securities` are in `ca_selections`. Warning only, no forced behavior change (user explicitly wants to keep viewing cash-inclusive NWC for peer trend comparison).
3. **Re-run `test_roundtrip.py`** against the Sept 8 `dashboard_page_state` schema extension (`dloc`, `value_level`, `non_op`, `last_edited_discount`) to confirm desktop↔web save/load still ties for the extended Dashboard state before calling #22 fully closed.
4. **Resolve the ~43-file VS Code Source Control anomaly** before the next commit. Run `git diff --stat` vs `git diff --ignore-all-space --stat`; if the gap confirms whitespace/line-ending churn, either commit it separately with an explicit "reformat" message or revert the untouched files. Set `"editor.formatOnSave": false` / `"files.eol": "\n"` in workspace settings to prevent recurrence.
5. **Scope DCF/GT page-level target-level display.** Currently only Dashboard shows the Minority-adjusted number; DCF and GT pages always show their own natural (controlling) output. Decide whether those pages should also surface "at Dashboard's selected level" — open design question, not yet scoped.
6. **Remove bypassed dead code, two places, after a bake-in period (not this week):**
   - Desktop DCF: ~20 old `_populate_*` methods + old `_compute_fv_for_assumptions` body (`Ui/dcf_page.py`).
   - Desktop GPC: unused `bridge_computed_labels_low/high` dicts and old keyed bridge label references (`ic_nctrl`, `ic_ctrl`, `eq_mkt_nctrl`, etc.) now superseded by the generic-slot renderer.
7. **Remaining GPC gaps:** private cash path (both surfaces stub to `None`), Company Name write path, `"TTM EBITDA"` label → `"TTM Adjusted EBITDA"` migration (needs session-string migration; line_key already correct since Sept 7).
8. **Dash input-remount UX** (GitHub issue #31): stop returning input-bearing tables from ordinary recalc callbacks. Projection Module first as the proof case. Unchanged from prior sessions.
9. **Step 9 — Theme + scroll standardization** now unblocked (surfaces share file format + engines). Extract `theme.py` roles to CSS custom properties; shared scroll-container helper.
10. **Housekeeping:** delete `cert.pem`/`key.pem`, empty `web/components/navbar.py`, Sept 7 scaffolding (`compare_schemas.py`, `probe_shapes.py`, `test_roundtrip.py`, `TEST_*.json`) after the #3 re-run above confirms clean; decide fast shallow-merge `session.py` only if cached loads ever lag.
11. **Analytics idea, not yet scoped (raised Sept 8):** now that Dashboard sits on the correct valuation level (post-#22), CSRP may be back-solvable/implied the same way Reverse-DCF already implies LTGR/STGR — turning CSRP into a cross-peer-comparable metric rather than a pure judgment call. Log in Analytics backlog (§5, GitHub #15); do not implement without a dedicated design pass.
12. GitHub issue triage backlog (not blocking #22): #24 refresh completion messaging, #26 WACC input alignment cosmetic, #33 international ticker research matrix, #15 Analytics backlog additions above.
13. Analytics on web — not blocking.
14. Final multi-machine sync check (brother's Windows machine) — not re-verified against current `4_application/`.