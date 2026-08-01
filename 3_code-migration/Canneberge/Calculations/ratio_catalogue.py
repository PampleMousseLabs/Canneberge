"""
ratio_catalogue.py
Canneberge — Ratio Catalogue.

Central home for calculation-layer ratios that aren't tied to any one
page's UI — shared across WACC, GPC, GT, and future NWC/DCF pages.
Organized into labeled sections (======), one per source statement
type. Currently: BS Calculations only. Future: IS Calculations
(Revenue CAGR, EBITDA CAGR, CapEx % of Sales, etc.).

Every function here takes a plain dict of raw line-item values for ONE
ticker at ONE period — same "raw dict in, computed dict out" pattern
already used in subject_is_bs_calc.py. Nothing in this file touches
the UI layer, session state, or any specific page's callbacks.

Input keys match the existing BS_LINES/IS_LINES naming convention from
app_state.py (cash, total_current_assets, current_ltd, st_debt, etc.)
— NOT literal StockAnalysis label strings. Callers are responsible for
resolving those keys from whatever source (fresh StockAnalysis pull,
PrivateFinancials, cached matrix) before calling in here.
"""

from typing import Optional, Dict


import math


def _to_float(raw) -> Optional[float]:
    if raw is None:
        return None
    try:
        val = float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val

def _to_pct_float(raw) -> Optional[float]:
    """Parses a percent-formatted string ('20.66%') into a decimal (0.2066)."""
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        val = float(text)
    except (ValueError, TypeError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val / 100.0

def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


# ============================================================
# BS CALCULATIONS
# ============================================================
# Source: Excel "BS Calculations" reference tab (Ratio Catalogue).
# Every formula below is a direct transcription — see module-level
# flags in the calling context for two confirmed-as-is oddities:
# Debt-free NWC (Excld. Cash)'s sign, and NPPE % of Revenue's PP&E term.

def debt_free_nwc_incl_cash(bs: Dict[str, Optional[float]]) -> Optional[float]:
    """
    Debt-free NWC (Incld. Cash) =
        Total Current Assets
        - [Total Current Liabilities - Current Portion LTD
           - Short-Term Debt - Current Portion Leases]
    """
    tca = bs.get("total_current_assets")
    tcl = bs.get("total_current_liab")
    current_ltd = bs.get("current_ltd") or 0.0
    st_debt = bs.get("st_debt") or 0.0
    current_leases = bs.get("current_leases") or 0.0

    if tca is None or tcl is None:
        return None

    non_debt_tcl = tcl - current_ltd - st_debt - current_leases
    return tca - non_debt_tcl


def debt_free_nwc_excl_cash(bs: Dict[str, Optional[float]]) -> Optional[float]:
    """
    Debt-free NWC (Excld. Cash) =
        [Total Current Assets - Cash & Equivalents]
        - [Total Current Liabilities - Current Portion LTD
           - Short-Term Debt - Current Portion Leases]

    Same as Debt-free NWC (Incld. Cash), but Cash is removed from the
    Total Current Assets term first.
    """
    cash = bs.get("cash")
    tca = bs.get("total_current_assets")
    tcl = bs.get("total_current_liab")
    current_ltd = bs.get("current_ltd") or 0.0
    st_debt = bs.get("st_debt") or 0.0
    current_leases = bs.get("current_leases") or 0.0

    if cash is None or tca is None or tcl is None:
        return None

    non_debt_tcl = tcl - current_ltd - st_debt - current_leases
    return (tca - cash) - non_debt_tcl


def total_debt(bs: Dict[str, Optional[float]]) -> Optional[float]:
    """
    Total Debt = Current Portion LTD + Short-Term Debt
                 + Current Portion Leases + Long-Term Debt
                 + Long-Term Leases

    Same five components as gpc_multiples.py's BEV net-debt calc.
    """
    keys = ["current_ltd", "st_debt", "current_leases", "lt_debt", "lt_leases"]
    values = [bs.get(k) for k in keys]
    if all(v is None for v in values):
        return None
    return sum(v or 0.0 for v in values)


def tic_book_value(
    debt: Optional[float], shareholders_equity: Optional[float]
) -> Optional[float]:
    """TIC (Book Value) = Total Debt + Shareholders' Equity. Includes cash."""
    if debt is None and shareholders_equity is None:
        return None
    return (debt or 0.0) + (shareholders_equity or 0.0)


def total_debt_to_tic(
    debt: Optional[float], tic: Optional[float]
) -> Optional[float]:
    return _div(debt, tic)


def total_debt_to_common_equity(
    debt: Optional[float], shareholders_equity: Optional[float]
) -> Optional[float]:
    return _div(debt, shareholders_equity)


def bev_book_value(
    tic: Optional[float], cash: Optional[float]
) -> Optional[float]:
    """BEV (Book Value) = TIC (Book Value) - Cash & Equivalents. Excludes cash."""
    if tic is None:
        return None
    return tic - (cash or 0.0)


def current_ratio(bs: Dict[str, Optional[float]]) -> Optional[float]:
    return _div(bs.get("total_current_assets"), bs.get("total_current_liab"))


def quick_ratio(bs: Dict[str, Optional[float]]) -> Optional[float]:
    tca = bs.get("total_current_assets")
    inventory = bs.get("inventory")
    tcl = bs.get("total_current_liab")
    if tca is None or tcl is None:
        return None
    return _div(tca - (inventory or 0.0), tcl)


def total_asset_turnover(
    revenue: Optional[float], total_assets: Optional[float]
) -> Optional[float]:
    return _div(revenue, total_assets)


def ar_turnover_days(
    revenue: Optional[float], bs: Dict[str, Optional[float]]
) -> Optional[float]:
    ar_total = (bs.get("accounts_receivable") or 0.0) + \
               (bs.get("receivables") or 0.0) + \
               (bs.get("other_receivables") or 0.0)
    turnover = _div(revenue, ar_total)
    return _div(365.25, turnover)


def inventory_turnover_days(
    revenue: Optional[float], inventory: Optional[float]
) -> Optional[float]:
    turnover = _div(revenue, inventory)
    return _div(365.25, turnover)


def ap_turnover_days(
    cogs: Optional[float], accounts_payable: Optional[float]
) -> Optional[float]:
    turnover = _div(cogs, accounts_payable)
    return _div(365.25, turnover)


def net_cash_operating_cycle(
    ar_days: Optional[float], inv_days: Optional[float], ap_days: Optional[float]
) -> Optional[float]:
    if ar_days is None or inv_days is None or ap_days is None:
        return None
    return ar_days + inv_days - ap_days


def nppe_pct_of_revenue(
    ppe: Optional[float], revenue: Optional[float],
    ppe_secondary: Optional[float] = None,
) -> Optional[float]:
    """
    NPPE % of Revenue = (Net PP&E + PP&E) / Revenue.

    Our schema currently only has one PP&E field ("ppe" / Net Property,
    Plant & Equipment). Confirmed by Ted: a second, distinct "Property,
    Plant & Equipment" line item exists on StockAnalysis and is a real
    safety catch-all (companies use one label or the other, never
    both) — currently always 0 in practice, not yet a field in
    BS_LINES. ppe_secondary defaults to None and is silently treated
    as 0 until/if that second field gets added to the schema; this
    function is already correct for that day without needing a rewrite.
    """
    if ppe is None and ppe_secondary is None:
        return _div(None, revenue)
    total_ppe = (ppe or 0.0) + (ppe_secondary or 0.0)
    return _div(total_ppe, revenue)


def debt_free_nwc_pct_of_revenue(
    nwc_value: Optional[float], revenue: Optional[float]
) -> Optional[float]:
    return _div(nwc_value, revenue)


def compute_bs_calculations(
    bs: Dict[str, Optional[float]], revenue: Optional[float], cogs: Optional[float]
) -> Dict[str, Optional[float]]:
    """
    Runs every BS Calculations formula for one ticker at one period.
    bs: raw BS line items (same keys as BS_LINES). revenue/cogs: raw
    IS line items for the same ticker/period (Revenue, Cost of Revenue).
    """
    nwc_incl = debt_free_nwc_incl_cash(bs)
    nwc_excl = debt_free_nwc_excl_cash(bs)
    debt = total_debt(bs)
    equity = bs.get("total_equity")
    tic = tic_book_value(debt, equity)
    bev = bev_book_value(tic, bs.get("cash"))

    ar_days = ar_turnover_days(revenue, bs)
    inv_days = inventory_turnover_days(revenue, bs.get("inventory"))
    ap_days = ap_turnover_days(cogs, bs.get("accounts_payable"))

    return {
        "debt_free_nwc_incl_cash": nwc_incl,
        "debt_free_nwc_excl_cash": nwc_excl,
        "total_debt": debt,
        "tic_book_value": tic,
        "total_debt_to_tic": total_debt_to_tic(debt, tic),
        "total_debt_to_common_equity": total_debt_to_common_equity(debt, equity),
        "bev_book_value": bev,
        "current_ratio": current_ratio(bs),
        "quick_ratio": quick_ratio(bs),
        "total_asset_turnover": total_asset_turnover(revenue, bs.get("total_assets")),
        "ar_turnover_days": ar_days,
        "inventory_turnover_days": inv_days,
        "ap_turnover_days": ap_days,
        "net_cash_operating_cycle": net_cash_operating_cycle(ar_days, inv_days, ap_days),
        "nppe_pct_of_revenue": nppe_pct_of_revenue(bs.get("ppe"), revenue),
        "debt_free_nwc_incl_cash_pct_revenue": debt_free_nwc_pct_of_revenue(nwc_incl, revenue),
        "debt_free_nwc_excl_cash_pct_revenue": debt_free_nwc_pct_of_revenue(nwc_excl, revenue),
    }

# ============================================================
# CAPITAL STRUCTURE (Ratio Catalogue subsection — WACC page)
# ============================================================
# Two distinct capital-structure bases, per Ted:
#   - Book basis: Total Debt / TIC (Book Value) — uses book equity,
#     "As of Valuation Date" only, single period (TTM).
#   - Market basis: Total Debt / MVIC (Market Value of Invested
#     Capital) — uses Market Cap, averaged across TTM:LFY-1 (2yr) or
#     TTM:LFY-4 (5yr) for the historical toggle options. Deliberately
#     a different ratio than the book one — not a bug, confirmed.
#
# Debt (Book) as a % of Equity is NOT computed independently — it's
# derived from whichever Debt/TIC-or-MVIC value is currently on
# screen: Debt%Equity = Debt%TIC / (1 - Debt%TIC).

from typing import List

_CAPSTRUCT_BS_LINE_ITEMS = {
    "current_ltd":   "current portion of long-term debt",
    "st_debt":       "short-term debt",
    "current_leases": "current portion of leases",
    "lt_debt":       "long-term debt",
    "lt_leases":     "long-term leases",
    "cash":          "cash & equivalents",
    "total_equity":  "shareholders' equity",
}
_MARKET_CAP_LINE_ITEM = "market cap"

def _build_lookup(rows: list, ticker: str) -> Dict[str, Dict[str, str]]:
    """
    Same pattern as gpc_multiples.py's _build_lookup — kept local
    rather than imported, consistent with this codebase's existing
    convention of not creating cross-module Calculations dependencies
    for simple row-filtering helpers.
    """
    ticker_lower = ticker.strip().lower()
    lookup: Dict[str, Dict[str, str]] = {}
    for row in rows:
        if str(row.get("Ticker", "")).strip().lower() != ticker_lower:
            continue
        key = str(row.get("Line Item", "")).strip().lower()
        lookup[key] = {
            k: v for k, v in row.items()
            if k not in ("Ticker", "Key", "Line Item")
        }
    return lookup

def _bs_dict_for_period(bs_rows: list, ticker: str, period: str) -> Dict[str, Optional[float]]:
    lookup = _build_lookup(bs_rows, ticker)
    result = {}
    for key, label in _CAPSTRUCT_BS_LINE_ITEMS.items():
        result[key] = _to_float(lookup.get(label, {}).get(period))
    return result

def _market_cap_for_period(ratio_rows: list, ticker: str, period: str) -> Optional[float]:
    lookup = _build_lookup(ratio_rows, ticker)
    return _to_float(lookup.get(_MARKET_CAP_LINE_ITEM, {}).get(period))

def debt_to_tic_book_from_bs(bs: Dict[str, Optional[float]]) -> Optional[float]:
    """Debt (Book) as a % of TIC — book basis. TIC includes cash."""
    debt = total_debt(bs)
    equity = bs.get("total_equity")
    tic = tic_book_value(debt, equity)
    return total_debt_to_tic(debt, tic)

def market_value_invested_capital(
    market_cap: Optional[float], debt: Optional[float]
) -> Optional[float]:
    """
    MVIC = Market Cap + Total Debt. Requires BOTH inputs present — a
    missing Market Cap does NOT mean $0 (the company almost certainly
    wasn't publicly traded that period, or wasn't scraped), it means
    unknown. Returning MVIC = Debt when Market Cap is missing produces
    a fabricated Debt/MVIC = 100%, which looks like a real ratio but
    isn't one.
    """
    if market_cap is None or debt is None:
        return None
    return market_cap + debt

def debt_to_mvic(debt: Optional[float], mvic: Optional[float]) -> Optional[float]:
    return _div(debt, mvic)

def historic_average(
    values: Dict[str, Optional[float]], periods: List[str]
) -> Optional[float]:
    present = [values[p] for p in periods if values.get(p) is not None]
    if not present:
        return None
    return sum(present) / len(present)

def debt_to_equity_from_debt_to_tic(
    debt_pct_tic: Optional[float]
) -> Optional[float]:
    """Debt (Book) as a % of Equity = Debt%TIC / (1 - Debt%TIC)."""
    if debt_pct_tic is None or debt_pct_tic == 1:
        return None
    return debt_pct_tic / (1 - debt_pct_tic)

def compute_debt_to_tic_book(
    bs_rows: list, ticker: str, period: str = "TTM"
) -> Optional[float]:
    """Book-basis Debt/TIC for one ticker at one period (default TTM)."""
    bs = _bs_dict_for_period(bs_rows, ticker, period)
    return debt_to_tic_book_from_bs(bs)

def compute_debt_to_mvic(
    bs_rows: list, ratio_rows: list, ticker: str, period: str
) -> Optional[float]:
    """Market-basis Debt/MVIC for one ticker at one period."""
    bs = _bs_dict_for_period(bs_rows, ticker, period)
    debt = total_debt(bs)
    market_cap = _market_cap_for_period(ratio_rows, ticker, period)
    mvic = market_value_invested_capital(market_cap, debt)
    return debt_to_mvic(debt, mvic)

def compute_historic_capital_structure(
    bs_rows: list, ratio_rows: list, ticker: str, periods: List[str]
) -> Optional[float]:
    """
    Average Debt/MVIC across the given periods. Caller supplies the
    period list: 2yr = ["TTM", "LFY", "LFY-1"], 5yr = TTM through
    LFY-4 (whatever historical_period_columns + ["TTM"] actually
    contains for this session).
    """
    per_period = {p: compute_debt_to_mvic(bs_rows, ratio_rows, ticker, p) for p in periods}
    return historic_average(per_period, periods)

_EFFECTIVE_TAX_RATE_LINE_ITEM = "effective tax rate"

def compute_effective_tax_rate(
    is_rows: list, ticker: str, fallback_rate: Optional[float] = None
) -> Optional[float]:
    """
    Effective Tax Rate, in priority order:
      1. 3-yr average of LFY, LFY-1, LFY-2 (all three required — TTM
         deliberately excluded, tax filing cyclicality makes TTM
         inconsistent as a standalone period; see Ted's note).
      2. LFY alone, if the 3-yr average isn't available.
      3. fallback_rate (the Home page's Tax Rate input), if neither
         historical option is available.
    """
    lookup = _build_lookup(is_rows, ticker)
    row_data = lookup.get(_EFFECTIVE_TAX_RATE_LINE_ITEM, {})

    three_yr = [_to_pct_float(row_data.get(p)) for p in ("LFY", "LFY-1", "LFY-2")]
    if all(v is not None for v in three_yr):
        return sum(three_yr) / 3

    lfy = _to_pct_float(row_data.get("LFY"))
    if lfy is not None:
        return lfy

    return fallback_rate