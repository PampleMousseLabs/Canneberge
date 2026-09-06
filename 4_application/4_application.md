# Phase 4: Canneberge Multi-Surface Application (Desktop & Web/PWA)

> **Current Status:** Step 8 (GPC Page) and Step 11a (Debt Schedule) are 100% complete, fully integrated, and mathematically validated. Core income-statement definitions (EBIT, EBITDA, Adjusted EBITDA, Net Interest) have been consolidated inside the shared calculations layer. Projected waterfalls across Subject Financials and the Projection Module are completely unified. 
> **Active Branch:** `main`
> **Active Directory:** `4_application/`
> **Last Updated:** September 5, 2026

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
2. **Thin UI Adapters:** Neither the PyQt UI nor the Dash UI contains business calculations. They only import from `Canneberge.Calculations`, `Canneberge.Sources`, etc. — confirmed holding true in practice (`web/lib/subject_metrics.py`, `web/pages/gpc.py`, `web/pages/debt_schedule.py` all delegate to `Canneberge.Calculations.*`, not reimplementing math).
3. **No Dual Logic Maintenance:** If a formula or data source changes, it is edited **once** in `Canneberge/` and automatically updates both UIs.
   * **Working rule adopted this session:** any change that touches definitions, schema (`IS_LINES`/`BS_LINES`), or resolvers goes into `Canneberge/` first; `web/` only gets "make it render" edits. The Web App and Desktop Subject Financials are now fully consolidated under this rule. The Desktop Projection Module is the sole legacy exception awaiting port-back (see Step 7d).
4. **Local Network Privacy:** No public cloud servers, no port forwarding. Tailscale connects tablet/other devices to the Chromebook host over the home network only.

---

## 3. Directory Layout (`4_application/`) — corrected to match reality

**Correction from earlier drafts of this doc:** the planned `desktop/` folder move never happened, and won't. `3_code-migration/` is frozen and untouched going forward; its contents were copied into `4_application/Canneberge/` once, and that copy is now the only actively-edited version. The PyQt6 desktop app runs directly from `4_application/Canneberge/`, same package the web app's `Canneberge.Calculations`/`Sources`/etc. imports pull from. There is no separate `desktop/` wrapper layer.

```text
4_application/
│
├── Canneberge/                   # SHARED CORE ENGINE + PyQt6 desktop UI
│   ├── Calculations/             # Math, DCF, GPC, WACC, debt schedules — shared by both UIs
│   │   ├── subject_is_bs_calc.py #   ✎ EBITDA definition corrected, adj_ebitda & net_interest added
│   │   ├── projection_resolve.py #   ✎ resolve_projection_waterfall() — the unified projected IS waterfall
│   │   ├── debt_schedule.py      #   Pure engine, unchanged — consumed as-is by web/pages/debt_schedule.py
│   │   └── gpc_metrics.py        #   ✎ forward EBITDA metrics renamed "Adjusted EBITDA" + toggle conversion maps
│   ├── Sources/                  # yfinance, FRED, StockAnalysis, MarketScreener — all live, none stubbed
│   ├── Services/                 # Multi-source coordination
│   ├── Transforms/                # Data normalization / mappings (sa_key.py — SBC/other_amortization are CFS-sourced)
│   ├── utils/                    # Shared helper functions
│   ├── Workers/                  # Async / Threading helpers
│   ├── Ui/                       # PyQt6 desktop pages — run directly, not moved to a separate folder
│   ├── app_state.py              # Application dataclasses · ✎ IS_LINES: ebitda relabeled, net_interest added, adj_ebitda added at bottom, sbc added
│   └── config.py                 # API keys & configuration
│
├── web/                          # SURFACE B: Dash tablet/browser UI
│   ├── assets/
│   │   ├── manifest.json         # PWA install config (Android home-screen)
│   │   ├── custom.css            # Scrollbar overrides, compact control classes, misc CSS fixes
│   │   └── (cert.pem / key.pem — leftover from an abandoned HTTPS test, unused by app.run(); candidate for deletion)
│   ├── lib/                      # Thin-adapter layer — where "single source of truth" is actually enforced
│   │   ├── subject_metrics.py    #   ✎ projection branch rewritten onto resolve_projection_waterfall(); CFS add-backs loaded; fallback debt-recalculator
│   │   ├── session_io.py
│   │   ├── gpc_data.py
│   │   └── ui_layout.py
│   ├── pages/
│   │   ├── home.py               # ✅ Built — full 1:1 conversion of desktop Home page
│   │   ├── source_data.py        # ✅ Built — real multi-source pipeline (see Step 7 note below)
│   │   ├── subject_financials.py # ✅ Built — Adjusted EBITDA + Net Interest rows now come from IS_LINES, no page-local math, compact toggle controls
│   │   ├── gpc.py                # ✅ Built — single shared <table>, basis_state.BEV/EQUITY isolation, compact controls, home basis default hydration
│   │   ├── debt_schedule.py      # ✅ Built — tranche grid, ReFi, +/- rows, totals; writes debt_page_state
│   │   └── dcf.py                # Empty placeholder file (proves nav routing only). Real DCF page not yet built.
│   ├── components/
│   │   └── projection_modal.py   # ✅ Built — full EBITDA→NI waterfall, Debt Schedule interest expense, pre-tax plug
│   └── app.py                    # Web entry (`python -m web.app`) — nav now includes Debt Schedule
│
├── requirements.txt
└── 4_application.md              # This document

---

4. Execution Roadmap (Step-by-Step)
Phase 4.1: Foundation & Scaffolding — Complete
 Step 1: Dependencies & Environment Setup
 Step 2: Scaffolding — (corrected: no desktop/ split happened — see Directory Layout above)
Phase 4.2: Web Skeleton & Tablet Access — Complete
 Step 3: Core Dash Shell (web/app.py) — multi-page, use_pages=True, running on 0.0.0.0:8050.
 Step 4: Android PWA Configuration — manifest.json in place.
 Step 5: Tablet Connectivity — resolved via Tailscale, not raw LAN IP as originally planned. Tested working from Chromebook's own browser and from tablet Chrome, both over the Tailscale tunnel. HTTPS (cert.pem/key.pem) was tried and abandoned — plain HTTP over Tailscale's already-encrypted tunnel was sufficient and simpler.
Phase 4.3: Page Migration (PyQt → Dash) — In Progress
 Step 6: Home Page — complete.
 Step 7: Real Source Data Pipeline — complete, not a placeholder. web/pages/source_data.py is fully wired to Canneberge.Services.source_data_service with per-source refresh buttons, a combined "Refresh All," background execution via DiskcacheManager, and live progress callbacks.
 Step 7b: Subject Financials — complete. Public/private branching through shared Calculations.subject_is_bs_calc.
This session: the page-local "Adjusted EBITDA" block (which duplicated math and briefly rendered the row twice) was removed; adj_ebitda and net_interest now render natively through the normal IS_LINES loop like every other calculated row. Projected columns (EBIT, Net Interest, Pretax, Taxes, Net Income) tie to the Projection Module to the dollar because both read resolve_projection_waterfall().
Vertical Compactness: Vertical padding on control elements reduced; radio buttons shrunk (btn-sm py-1 px-2) to maximize screen estate for financials.
Projected Interest Expense display: Flipped to negative (-abs(v)) in display layer only, ensuring visual parity with historical negative interest while preserving positive cost math in the core calculations.
 Step 7c: Projection Module — complete. Row set matches and exceeds desktop:
Rows added this session: Taxes, Net Income, Net Income Margin (%). Projected Other Amortization $ and SBC $ now display as % × Revenue (previously only historicals showed).
Waterfall reordered into a true statement: Adjusted EBITDA → Less D&A → Less Other Amort → Less SBC → EBIT → Net Interest Income/(Expense) → +Other Adjustments → Taxes → Net Income → CapEx.
+Other Adjustments is now a PRE-tax plug on public NFY–NFY+2 (analyst_NI / (1−t) − EBT_before_adj), so the column actually foots top-to-bottom and the residual the user reads off NFY+2 to hand-enter in NFY+3 is an interpretable pre-tax number. Desktop's version computed it after-tax while displaying it above the Taxes row — that inconsistency is fixed on web and desktop.
Historical Taxes now show the actual reported figure, not pretax × Home tax rate.
Net Interest is signed: historical = Interest Income − |Interest Expense|; projected = −(Debt Schedule interest expense) with projected interest income deliberately assumed zero (no defensible basis to forecast it yet).
All projected display values come straight from resolve_projection_dollars() — the modal no longer maintains a second local waterfall.
 Step 7d: Income-Statement Definition Consolidation (shared core) — complete. Root cause found this session: compute_is_calculated was labelling Gross Profit − Operating Expenses as "ebitda", and since StockAnalysis OpEx already includes D&A, that figure was really EBIT. Meanwhile MarketScreener forward EBITDA is SBC-adjusted. Net effect was a silent definition change at TTM→NFY (Adobe: 36.7% → 47.8% "margin expansion" that was purely definitional, then compounded through every projected year). Fix — edited once in Canneberge/:
subject_is_bs_calc.py: EBIT = GP − OpEx; EBITDA = EBIT + D&A + Other Amortization; adj_ebitda = EBITDA + SBC; net_interest (signed) added to the return dict.
app_state.py IS_LINES: "ebitda" relabeled "EBITDA (before SBC add-back)"; ("net_interest", …, True, True) inserted after interest_income; ("stock_based_compensation", ..., False, False) inserted before adj_ebitda; ("adj_ebitda", …, True, True) appended at the very bottom (derived row, keeps historical statements tying to the 10-K).
projection_resolve.py: new resolve_projection_waterfall(); resolve_projection_dollars() extended with ms_net_income, tax_rate, net_interest_by_period and now returns other_amort/sbc/ebit/net_interest/other_adj/pretax_income/taxes/net_income per period.
web/lib/subject_metrics.py: SBC and other_amortization (both CFS-sourced per sa_key.py) are now loaded into the historical raw dict so the calculated EBITDA rows can use them; projection branch rewritten to call the shared waterfall; _normalise_rate() accepts 0.21/21/"21%".
Desktop app synchronized: Both subject_financials_page.py and projection_module_page.py refactored. Desktop historical Adjusted EBITDA now correctly computes and renders with CFS-sourced SBC (ADBE LFY-4 Adjusted EBITDA = EBITDA + 1,069). Projected EBITDA, EBIT, and Taxes match the web implementation.
 Step 8: GPC Page — complete.
 Compacted Control Strip: Vertical dead space compressed significantly. Input widths minimized, labels sized down, and radio toggle buttons shrunk (btn-sm py-1 px-2) to keep the focus entirely on valuation data.
 State Persistence (BEV / Equity separation): Split-basis state buckets fully operational. metric_cols, selected_high, selected_low, and weights are saved independently under basis_state.BEV and basis_state.EQUITY. Switching modes protects dynamic data against unmounted state-wiping (via ctx.triggered_id checking). Type-safe _safe_dict() wrapper prevents page crashes on legacy list-to-dict sessions.
 Home Default Hydration: GPC page automatically reads Home’s basis_of_value on page load. If Home is set to "Equity Value", GPC loads with Equity toggled; otherwise, defaults to BEV. Local toggle remains fully functional.
 Column alignment solved for real this session. Root cause: header and body were two separate <table> elements, so the browser sized their columns independently. Fix: one shared <table> with <colgroup> + <thead id=gpc-header-container> + <tbody id=gpc-body-container>; tableLayout: fixed; a _col_style() helper setting width/minWidth/maxWidth together; Statistics/Selected/Subject/Weighting tables use the same four leading columns (_leading_cells()) instead of one wide cell trying to emulate four. The split header/body callback design (dropdowns don't remount on exclude toggles) was preserved.
 DuplicateCallback crash on startup fixed — restore_gpc_static_state needed prevent_initial_call='initial_duplicate' because it writes gpc-exclude-store with allow_duplicate=True.
 Weighting inputs verified live-wired (Input({"type":"gpc-weight","index":ALL},"value") already in the render callback — earlier note in this doc was stale). Fixed a latent bug where FMV High/Low rows had 2 cells vs. 1+N in the weight row.
 Forward metrics renamed "NFY / NFY+1 / NFY+2 Adjusted EBITDA" in gpc_metrics.py (+ toggle conversion maps). gpc.py requests "adj_ebitda" for the subject on those periods only — comps come from MarketScreener (adjusted), so this is apples-to-apples; TTM stays conventional on both sides. gpc_multiples.py unchanged (its comp-side source routing was already correct).
 ⚠️ Bridge — BEV-mode formula chain only. Desktop's Equity-mode branch (eq_nctrl → eq_mkt_ctrl → eq_nonmkt_ctrl) not ported.
 ⚠️ Private-company cash path stubbed to None in the Bridge.
 ⚠️ NWC Surplus/Deficit and Non-Operating Assets, Net remain manual placeholder inputs — NWC page (Step 11b) should feed the first one.
 ⚠️ Company Name column in the ticker grid still blank on the live page even though gpc_company_names is read — trace whether Home is actually writing names into the session (yfinance lookups may be failing silently).
 ⚠️ "TTM EBITDA" label: comps use the raw StockAnalysis ebitda row, subject now uses conventional EBITDA from compute_is_calculated. If SA's row is EBIT-like for a given ticker the label is misleading. Low priority — historical multiples are rarely used.
 Step 9: Theme System — not started. Web's dark styling (Bootstrap DARKLY) coincidentally resembles desktop's One Dark Pro, not the true default (Slate & Gold). Extract theme.py color roles into CSS custom properties before more pages accumulate hardcoded hex. Add to scope: a shared scroll-container helper in ui_layout.py (overflowX/Y: auto, minWidth: 0, optional maxHeight) so every wide table scrolls internally the way the Projection Module now does — currently only the modal has the visible/grabbable scrollbar treatment.
 Step 10: DCF Page — not started beyond the placeholder. Inputs it needs are now largely available in session: projected Adjusted EBITDA / EBIT / taxes / net income (Projection Module), interest & net borrowing (Debt Schedule). Still missing: NWC (Step 11b), WACC. Two bugs fixed earlier in the desktop's valuation_surface.py/dcf_page.py (EBITDA-multiple TV used final_fcf; H-Model sensitivity used approximated residual FCF) apply automatically via shared Calculations/.
 Step 11: Debt Schedule, NWC, WACC, GT pages
 11a: Debt Schedule — built this session. web/pages/debt_schedule.py reuses Calculations/debt_schedule.py unchanged. Rate Basis select, up to 20 tranche rows, +/− row buttons, per-row ↻ ReFi (issues at prior maturity, +5 yrs), per-tranche interest by period, Total Interest / Ending Debt / Net Borrowing rows. Persists to session-store["debt_page_state"] in the same shape desktop writes (rate_basis, row_count, rows) plus cached engine outputs (interest_expense_by_period, ending_debt_by_period, net_borrowing_by_period, projected_interest) so consumers don't recompute. Totals verified equal to desktop. Wired into the Projection Module and subject_metrics.py (signed net interest) — the $500–600M/yr that was hiding inside +Other Adjustments now sits on its own row and the plug shrank accordingly. Known limitation: intentionally elementary (no amortizing principal, no revolver, no rate curves) — upgrade candidate after the remaining pages exist.
Plumbing Resilience: If a loaded session only carries tranche rows (saved prior to engine caches), subject_metrics.py automatically reconstructs periods/boundaries and re-calculates the debt schedule on the fly using _interest_map_from_debt_state so the waterfall never breaks.
 11b: NWC — next.
 11c: GT — after DCF; fairly independent.
 11d: WACC — needed before DCF can produce a value; sequence TBD (may slot between NWC and DCF).
Phase 4.4: Hardening & Parity Check — Not Started
 State synchronization confirmed working for Home/Subject Financials/Source Data/GPC/Debt Schedule via dcc.Store — extend to remaining pages as built.
 Desktop regression pass after this session's shared-core edits completed — verified 100% functional, no crashes.
 Final multi-machine sync check (brother's Windows machine) — not yet re-verified against the current 4_application/ structure.
5. Known Issues / Technical Debt Log
Item	Status
cert.pem / key.pem in web/assets/	Unused leftovers from an abandoned HTTPS test. Candidate for deletion.
web/components/navbar.py	Empty file — app.py builds its navbar inline. Dead scaffolding, not a bug.
GPC Weighting inputs not live	Resolved — were already wired; doc was stale. FMV row cell-count bug fixed.
GPC header/body column drift	Resolved — single shared table + colgroup + fixed widths.
GPC DuplicateCallback on startup	Resolved — prevent_initial_call='initial_duplicate'.
GPC selections lost on BEV↔Equity toggle	Resolved — per-basis basis_state buckets.
Projection Module missing Taxes / NI / NI margin rows	Resolved.
Projected OA $ / SBC $ not shown	Resolved.
EBITDA definition flips at TTM→NFY	Resolved in shared core (Step 7d).
Subject Financials Adjusted EBITDA rendered twice	Resolved — page-local block removed; row comes from IS_LINES.
Desktop projection_module_page.py out of sync	Resolved — desktop successfully ported to shared core math.
Oversized Web Toggles and Control Bars	Resolved — shrunk GPC and Subject Financials control cards. CSS class added.
Projected interest expense blank on Subject Financials page load	Resolved — fallback notes-driven recalculator added.
GPC Bridge — Equity mode	Not ported; only BEV chain exists.
GPC Bridge — private-company cash	Stubbed to None.
GPC ticker grid — Company Name column	Blank on live page; investigate Home → session write path.
GPC "TTM EBITDA" label vs. definition	Comps raw SA row, subject conventional EBITDA. Low priority.
Projected interest income	Assumed zero by design; revisit if a cash-balance model is added.
Debt Schedule depth	No amortization / revolver / rate curves. Upgrade after NWC/DCF/GT.
Scrollbar consistency	Only the Projection Module has the explicit ::-webkit-scrollbar + overflow treatment. Standardize via ui_layout.py helper (folded into Step 9).
Theme system	Not started — see Step 9.
dcc.Dropdown dark-theme styling	Resolved earlier via dbc.min.css + className="dbc" — reuse on any page with dropdowns.
Input-in-table-cell right-alignment	Resolved earlier — marginLeft: "auto" on the input's own style.
Dash allow_duplicate pattern	Reminder: any callback with allow_duplicate=True must set prevent_initial_call=True or 'initial_duplicate'. Bit us once; will again on new pages.
6. Developer Cheatsheet / Common Commands
Running the Desktop App
Bash

cd ~/PampleMousseLabs/ProjectCanneberge/4_application
python -m Canneberge.main
Running the Web / Tablet App (Local Host)
Bash

cd ~/PampleMousseLabs/ProjectCanneberge/4_application
python -m web.app
# Access locally: http://127.0.0.1:8050
# Access on tablet/other devices: http://<tailscale-ip>:8050
Session-state keys now in use (session-store)
projection_page_state · gpc_page_state (incl. basis_state.BEV/EQUITY) · debt_page_state · private_is_data / private_bs_data · reserved: nwc_page_state, wacc_page_state, dcf_page_state, gt_page_state, dashboard_page_state (all preserved by Home autosync already).

Git Routine (End of Day)
Bash

git add .
git commit -m "Progress update: Phase 4 Step X"
git push

7. Next Steps (Prioritized)
Step 11b — NWC page. Send Canneberge/Ui/nwc_page.py + any Calculations/ module it imports. Build web/pages/nwc.py on the same pattern as Debt Schedule (pure engine reuse, nwc_page_state, cached outputs). Wire its surplus/deficit into the GPC Bridge placeholder.
Step 11d — WACC page (or confirm DCF can start with a manual WACC input).
Step 10 — DCF page. Consumes Projection Module (via subject_metrics), Debt Schedule (interest, net borrowing), NWC, WACC. Terminal value panel, sensitivity table, reverse-DCF.
Step 11c — GT page.
Step 9 — Theme + scroll standardization once page count stabilizes.
Close remaining GPC gaps: Equity-mode bridge, private cash, Company Name column.