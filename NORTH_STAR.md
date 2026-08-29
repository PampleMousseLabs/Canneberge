# NORTH_STAR.md
### Personal Bloomberg Terminal — Master Vision & Roadmap

**Owner:** [Your Name]  
**Started:** August 2026  
**Last revised:** August 2026  
**Status:** Active — Canneberge foundation shipped, expansion planned

---

## 1. Mission Statement

Build a self-hosted, ad-free, locally-run suite of financial applications that
collectively replicate — and in targeted areas surpass — the analytical
capability of institutional platforms like Bloomberg Terminal, at zero
recurring subscription cost.

The suite is designed for a single-user practitioner with
institutional valuation and capital markets experience, prioritizing
**actionable analytical insight** over decorative dashboards or academic
completeness.

---

## 2. Guiding Principles

1. **Actionability over academia.** Every module must produce output that
   informs a real trade, valuation conclusion, or risk decision. If it
   doesn't move a decision, it doesn't ship.
2. **Ad-free, local-first.** All apps run on personal hardware (laptop or
   home-server model). No SaaS dependency. No ad revenue models.
3. **Modular, not monolithic.** Each app is independently useful and
   independently deployable. Shared calculation logic lives in reusable
   Python modules; UI stays isolated per app.
4. **Pure math, separated from UI.** Calculation engines (`Calculations/`)
   never import PyQt or UI frameworks. This preserves portability to future
   web/tablet clients and enables CLI + batch testing.
5. **Institutional rigor, practical shortcuts.** Where full modeling is
   overkill, use documented proxies (e.g., Book Debt ≈ FV Debt) and clearly
   label them. Never hide assumptions.
6. **Own the data pipeline.** Prefer scraping / free APIs / cached datasets
   over paid feeds until scale demands otherwise.

---

## 3. The Five-App Ecosystem

### App 1 — Canneberge (Fair Value / Fundamental Valuation) ✅ *In Progress*

**Purpose:** Institutional-grade DCF-based fair value platform with
peer-relative multiples and reverse-DCF market-implied growth analysis.

**Core Capabilities (shipped):**
- Full DCF engine (FCFF & FCFE toggle, WACC / Ke dynamic discount rate)
- WACC page with beta relevering, capital structure controls, FRED-linked
  risk-free rate & corporate spreads
- Debt Schedule (tranche-level, projected interest expense feeds DCF FCFE)
- NWC modeling with GPC-relative ratio calibration
- Subject Financials aggregation (IS/BS) from StockAnalysis or manual private
  input
- GT (Guideline Transactions) and GPC (Guideline Public Companies) multiples
- Reverse-DCF (Gordon Growth + H-Model) with FCFE bridge and market-implied
  LTGR / H-solver
- Valuation Surface (WACC × LTGR sensitivity, 3D)
- Session save/load (JSON), theme system (Slate & Gold, One Dark Pro,
  GitHub Light), font scaling
- Analytics tab (FCFF ↔ FCFE reconciliation diagnostics + friction ratios)

**Planned Capabilities:**
- **PVGO / Growth Decomposition Engine** — $/share value of growth vs
  zero-growth base value, cross-ticker comparison for mispricing signals
- **Session caching optimization** — save scraped source data into session
  JSON to eliminate boot-time refresh penalty
- **Pure-math refactor** for DCF sensitivity table & valuation surface
  (extract from UI widget calls into `Calculations/dcf_engine.py`)
- **Basis of Value toggle propagation** — Enterprise vs Equity Value flowing
  through GPC/GT multiple construction
- **Live macro shock injection** (from App 2)

---

### App 2 — Macro & Econometrics (Rate & Cycle Modeling) 🔜 *Planned*

**Purpose:** Model macroeconomic variables (Fed funds path, yield curve,
credit spreads, employment data, inflation) and translate shocks into
actionable per-security or per-portfolio impacts.

**Core Capabilities (planned):**
- Fed funds path forecasting (implied from Fed Funds futures + Taylor rule
  overlays)
- Yield curve modeling (2s/10s, real rates, breakevens)
- Credit spread tracking (IG, HY, distressed) linked to Canneberge's Kd
- Macro release calendar (FOMC, CPI, NFP, GDP, PCE)
- **Shock engine:** input a scenario ("Fed +50bps at next FOMC"), output
  delta-WACC, delta-Ke, delta-target-price for every ticker in watchlist
- Econometric regressions (rates → sector performance, spreads → equity
  returns)
- Integration hook: macro shocks feed directly into Canneberge's DCF
  assumptions for scenario valuation

---

### App 3 — Derivatives & Trade Engineering (DerivaGem++) 🔜 *Planned*

**Purpose:** Full derivatives pricing and trade-structuring platform,
extending beyond DerivaGem to include live options data, multi-leg strategy
construction, and payoff visualization.

**Core Capabilities (planned):**
- Live options chain ingestion (Yahoo Finance, Nasdaq, or CBOE feeds)
- Vanilla pricing (Black-Scholes, Binomial, Trinomial)
- Exotic pricing (Asian, Barrier — up-and-in / down-and-out, Lookback,
  Digital)
- Greeks calculation (Δ, Γ, Θ, ν, ρ) across single-leg and multi-leg
  positions
- **Multi-leg trade constructor:** input target price + risk tolerance,
  output optimal strategy (spreads, condors, ratio backspreads, collars)
- Payoff diagrams with theme-consistent charts (matches Canneberge visual
  system)
- Integration hook: pulls target prices from Canneberge, macro shocks from
  App 2, outputs hedged exposure recommendations

---

### App 4 — Home / News Aggregator / Portfolio Tracker 🔜 *Planned*

**Purpose:** Personal command center with ad-free news, portfolio positions,
watchlists, and macro release feeds. Serves as the daily "start here" app.

**Core Capabilities (planned):**
- RSS-based news aggregator (filtered by ticker watchlist and macro
  keywords)
- Ad-free reading experience — strip promotional content, focus on raw
  wire/analyst reports
- Portfolio tracker (positions, cost basis, unrealized P&L, dividend
  calendar)
- Watchlist with live price scroll and technical alerts
- Macro release calendar with countdown timers
- Integration hook: click a ticker → opens Canneberge with that ticker
  pre-loaded; click a macro event → opens App 2 with shock scenario
  pre-staged

---

### App 5 — Credit & Distressed Debt Platform 🔜 *Planned*

**Purpose:** Credit rating engine and distressed debt analytics. Focused on
public corporate debt pricing and default probability estimation. Ambition:
"10% of Moody's, miles ahead of what most firms actually use."

**Core Capabilities (planned):**
- Proxy credit rating model (Moody's/S&P-style scorecard using financial
  ratios, business risk, industry risk)
- Yield-to-Maturity / Yield-to-Worst calculators
- Default probability modeling (Merton, KMV, reduced-form)
- Recovery rate estimation by seniority and industry
- Distressed debt valuation (option-theoretic equity residual)
- Fair Value of Debt engine — plugs directly back into Canneberge to
  replace the current μ = 1.0 book-value proxy
- Integration hook: feeds real FV Debt into Canneberge's DCF bridge and
  Analytics tab

---

## 4. Cross-App Architecture Principles

### Data Flow
[Source Data Layer] → [Calculation Engines (Pure Python)] → [App UIs]
↓
[Shared JSON / SQLite cache]
↓
[Cross-app integration hooks]

### Shared Infrastructure (to be built)
- **Common data cache:** shared local database (SQLite) for scraped
  financials, prices, macro series, options chains
- **Common theme system:** extract Canneberge's `theme.py` into a shared
  package installable across all 5 apps
- **Common session/config system:** unified user preferences, watchlists,
  portfolio positions
- **Common calculation library:** `finlib/` package with WACC, DCF,
  Black-Scholes, credit ratios, macro econometrics — importable by any app

### Deployment Model
- **Phase 1 (current):** Local Windows desktop, PyQt6 GUI, single-user
- **Phase 2:** Home server hosting — apps served to browser or tablet via
  Reflex/Flet/Streamlit wrapper
- **Phase 3 (long-term):** Cross-platform (Mac/Linux/mobile via Flutter or
  PWA)

---

## 5. Immediate Next Priorities (Q3/Q4 2026)

### Canneberge
1. **PVGO / Growth Decomposition** in Analytics tab (next build)
2. Session caching to eliminate boot-time refresh (~40s → ~5s)
3. DCF sensitivity engine pure-math refactor (kill Qt widget calc dependency)
4. Expand GPC set beyond current 9-ticker mix for QA testing
5. Basis of Value toggle downstream propagation

### Cross-Suite Foundation
1. Extract shared theme/font/utility modules into `finlib/` package
2. Design SQLite cache schema for cross-app data sharing
3. Decide on integration protocol (local API? shared filesystem? IPC?)

---

## 6. What This Is NOT

- **Not a SaaS product.** No monetization plan. No user acquisition.
- **Not a research platform for publication.** Rigor is high but the
  audience is one person.
- **Not a replacement for execution infrastructure.** No order routing,
  no broker integration (yet). Analytical output feeds manual execution.
- **Not open-source (initially).** Private repo. May open specific modules
  later if there's a reason to.

---

## 7. Revision Log

| Date | Change |
|------|--------|
| 2026-08-28 | Initial draft. Documented 5-app vision, Canneberge status, next-priority PVGO build. |

---

## 8. Anti-Scope-Creep Reminders

Every time a new feature idea appears, run it through this filter:

1. **Which app does it belong to?** If none, it's a distraction.
2. **Does it produce actionable output?** If not, deprioritize.
3. **Does it require paid data?** If yes, find a free proxy first.
4. **Would it break the "pure math / isolated UI" principle?** If yes,
   redesign before building.
5. **Am I building this because it's cool, or because it moves a decision?**
   Only the second answer justifies build time.

---

*"Basically, I want a Bloomberg Terminal for free. And I'm not scared to code it."*