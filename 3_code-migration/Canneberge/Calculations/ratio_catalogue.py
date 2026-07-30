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


def _to_float(raw) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None


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