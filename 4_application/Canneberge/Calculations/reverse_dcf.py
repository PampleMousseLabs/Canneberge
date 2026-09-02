"""
reverse_dcf.py
Canneberge — Reverse-DCF Calculation & Input Extraction Module.

Pure calculation and data-assembly layer. Extracts the exact light-blue
inputs shown in the Excel verification model for any GPC ticker or Subject
Company, and computes the FCFE bridge, reconciliation term A, and implied
LTGR / H-Model parameters.
"""

from typing import Optional, Dict, List, Any

from Canneberge.Calculations.gpc_multiples import get_ticker_metric
from Canneberge.Transforms.sa_key import get_sa_label
from Canneberge.utils.sa_utils import build_lookup, to_float
from Canneberge.Calculations.ratio_catalogue import (
    debt_free_nwc_incl_cash,
    debt_free_nwc_excl_cash,
)

_H_MODEL_VARS = ("Ga", "Gn", "H")

def extract_ticker_inputs(
    ticker: str,
    sa_results: Dict[str, list],
    ms_rows: list,
    fred_rows: list,
    wacc_beta_val: Optional[float],
    erp_val: Optional[float],
    nwc_exclude_cash: bool = True,
) -> Dict[str, Any]:
    ticker_lower = ticker.strip().lower()
    is_rows = sa_results.get("IS", [])
    bs_rows = sa_results.get("BS", [])
    cfs_rows = sa_results.get("CFS", [])
    ratio_rows = sa_results.get("Ratios", [])

    is_lookup = build_lookup(is_rows, ticker_lower)
    bs_lookup = build_lookup(bs_rows, ticker_lower)
    cfs_lookup = build_lookup(cfs_rows, ticker_lower)
    ratio_lookup = build_lookup(ratio_rows, ticker_lower)

    market_cap = to_float(ratio_lookup.get(get_sa_label("market_cap"), {}).get("TTM"))

    revenue = {
        "LFY": to_float(is_lookup.get(get_sa_label("revenue"), {}).get("LFY")),
        "TTM": to_float(is_lookup.get(get_sa_label("revenue"), {}).get("TTM")),
        "NFY": get_ticker_metric(is_rows, ms_rows, bs_rows, ticker_lower, "NFY", "revenue"),
        "NFY+1": get_ticker_metric(is_rows, ms_rows, bs_rows, ticker_lower, "NFY+1", "revenue"),
        "NFY+2": get_ticker_metric(is_rows, ms_rows, bs_rows, ticker_lower, "NFY+2", "revenue"),
    }

    net_income = {
        "LFY": to_float(is_lookup.get(get_sa_label("net_income"), {}).get("LFY")),
        "TTM": to_float(is_lookup.get(get_sa_label("net_income"), {}).get("TTM")),
        "NFY": get_ticker_metric(is_rows, ms_rows, bs_rows, ticker_lower, "NFY", "net_income"),
        "NFY+1": get_ticker_metric(is_rows, ms_rows, bs_rows, ticker_lower, "NFY+1", "net_income"),
        "NFY+2": get_ticker_metric(is_rows, ms_rows, bs_rows, ticker_lower, "NFY+2", "net_income"),
    }

    rev_ttm = revenue.get("TTM")
    da_ttm_raw = to_float(cfs_lookup.get(get_sa_label("depreciation_amortization"), {}).get("TTM"))
    da_ttm = abs(da_ttm_raw) if da_ttm_raw is not None else None
    depr_pct = (da_ttm / rev_ttm) if (da_ttm is not None and rev_ttm) else None

    capex_ttm_raw = to_float(cfs_lookup.get(get_sa_label("capex"), {}).get("TTM"))
    capex_ttm = abs(capex_ttm_raw) if capex_ttm_raw is not None else None
    capex_pct = (capex_ttm / rev_ttm) if (capex_ttm is not None and rev_ttm) else None

    nwc_keys = ["total_current_assets", "total_current_liab",
                "current_ltd", "st_debt", "current_leases", "cash",
                "st_investments", "cash_short_term_investments"]
    bs_ttm = {k: to_float(bs_lookup.get(get_sa_label(k), {}).get("TTM")) for k in nwc_keys}
    nwc_val = debt_free_nwc_excl_cash(bs_ttm) if nwc_exclude_cash else debt_free_nwc_incl_cash(bs_ttm)
    nwc_pct = (nwc_val / rev_ttm) if (nwc_val is not None and rev_ttm) else None

    risk_free_rate = None
    for row in fred_rows:
        if str(row.get("SeriesID", "")).strip().upper() == "DGS20":
            val = row.get("LatestValue")
            if val is not None:
                risk_free_rate = float(str(val).replace(",", "")) / 100.0
            break

    return {
        "ticker": ticker.upper(),
        "market_cap": market_cap,
        "revenue": revenue,
        "net_income": net_income,
        "depr_pct": depr_pct,
        "capex_pct": capex_pct,
        "nwc_pct": nwc_pct,
        "risk_free_rate": risk_free_rate,
        "relevered_beta": wacc_beta_val,
        "equity_risk_premium": erp_val,
    }

def compute_cost_of_equity(risk_free_rate, beta, erp):
    if risk_free_rate is None or beta is None or erp is None:
        return None
    return risk_free_rate + (beta * erp)

def build_fcfe_schedule(revenue_prior, revenue_explicit, net_income_explicit, depr_pct, capex_pct, nwc_pct, force_terminal_capex_equals_da=True):
    if revenue_prior is None or depr_pct is None or capex_pct is None or nwc_pct is None:
        return None
    if not revenue_explicit or len(revenue_explicit) != len(net_income_explicit):
        return None
    if any(r is None for r in revenue_explicit) or any(ni is None for ni in net_income_explicit):
        return None
    schedule = []
    prior_rev = revenue_prior
    for t in range(len(revenue_explicit)):
        rev_t = revenue_explicit[t]
        ni_t = net_income_explicit[t]
        depr_t = rev_t * depr_pct
        capex_t = rev_t * capex_pct
        if t == len(revenue_explicit) - 1 and force_terminal_capex_equals_da:
            capex_t = depr_t
        delta_nwc_t = (rev_t - prior_rev) * nwc_pct  # <-- ΔNWC LINE 89
        fcfe_t = ni_t + depr_t - capex_t - delta_nwc_t
        schedule.append({
            "year_index": t + 1,
            "revenue": rev_t,
            "net_income": ni_t,
            "depreciation": depr_t,
            "capex": capex_t,
            "delta_nwc": delta_nwc_t,
            "fcfe": fcfe_t,
        })
        prior_rev = rev_t
    return schedule

def compute_reconciliation_a(market_cap, fcfe_schedule, ke):
    if market_cap is None or not fcfe_schedule or ke is None or ke <= -1:
        return None
    n = len(fcfe_schedule)
    pv_sum = sum(yr["fcfe"] / ((1 + ke) ** yr["year_index"]) for yr in fcfe_schedule)  # <-- PVFCFE LINE 108
    return (market_cap - pv_sum) * ((1 + ke) ** n)

def solve_gordon_growth_ltgr(a, ke, fcfe_n):
    if a is None or ke is None or fcfe_n is None:
        return {"value": None, "is_valid": False, "flags": ["missing_inputs"]}
    if fcfe_n <= 0:
        return {"value": None, "is_valid": False, "flags": ["fcfe_n_not_positive"]}
    denom = fcfe_n + a
    if denom == 0:
        return {"value": None, "is_valid": False, "flags": ["zero_denominator"]}
    v = (a * ke - fcfe_n) / denom
    flags = []
    if v < 0:
        flags.append("implied_ltgr_negative")
    if v >= ke:
        flags.append("implied_ltgr_gte_ke")
    return {"value": v, "is_valid": len(flags) == 0, "flags": flags}

def solve_h_model(a, ke, fcfe_n, ga=None, gn=None, h=None, solve_for=None, full_fade_convention=True):
    flags = []
    out = {"value": None, "is_valid": False, "flags": flags, "solved_for": solve_for}
    if a is None or ke is None or fcfe_n is None:
        flags.append("missing_inputs")
        return out
    if fcfe_n <= 0:
        flags.append("fcfe_n_not_positive")
        return out
    supplied = {"Ga": ga, "Gn": gn, "H": h}
    none_keys = [k for k, v in supplied.items() if v is None]
    if solve_for is None:
        if len(none_keys) != 1:
            flags.append("exactly_one_unknown_required")
            return out
        solve_for = none_keys[0]
    out["solved_for"] = solve_for
    if gn is not None and gn >= ke:
        flags.append("gn_supplied_gte_ke")
        return out
    try:
        h_eff_factor = 0.5 if full_fade_convention else 1.0
        if solve_for == "H":
            numer = a * (ke - gn) - fcfe_n * (1 + gn)
            denom = fcfe_n * (ga - gn)
            if denom == 0:
                flags.append("zero_denominator")
                return out
            value = (2 * numer / denom) if full_fade_convention else (numer / denom)
        elif solve_for == "Ga":
            h_eff = h * h_eff_factor if h is not None else 0
            if h_eff == 0:
                flags.append("h_zero")
                return out
            value = gn + (a * (ke - gn) - fcfe_n * (1 + gn)) / (fcfe_n * h_eff)
        else:
            h_eff = h * h_eff_factor if h is not None else 0
            denom = a + fcfe_n * (1 - h_eff)
            if denom == 0:
                flags.append("zero_denominator")
                return out
            value = (a * ke - fcfe_n * (1 + h_eff * ga)) / denom
    except ZeroDivisionError:
        flags.append("zero_denominator")
        return out
    out["value"] = value
    out["is_valid"] = len(flags) == 0
    return out

def compute_ttm_fcfe(ttm_net_income, ttm_revenue, depr_pct, capex_pct):
    """
    Computes TTM FCFE using TTM as the base period.
    delta_nwc = 0 at base period (no prior period to diff against).
    """
    if any(v is None for v in [ttm_net_income, ttm_revenue, depr_pct, capex_pct]):
        return None
    depr = ttm_revenue * depr_pct
    capex = ttm_revenue * capex_pct
    return ttm_net_income + depr - capex  # delta_nwc = 0


def extract_all_gpc_inputs(
    tickers, sa_results, ms_rows, fred_rows,
    wacc_beta_vals, erp_val, nwc_exclude_cash=True,
):
    all_inputs = {}
    for ticker in tickers:
        ticker_upper = ticker.strip().upper()
        beta = wacc_beta_vals.get(ticker_upper)
        try:
            inputs = extract_ticker_inputs(
                ticker=ticker_upper,
                sa_results=sa_results,    # ← pass the whole flat pool
                ms_rows=ms_rows,
                fred_rows=fred_rows,
                wacc_beta_val=beta,
                erp_val=erp_val,
                nwc_exclude_cash=nwc_exclude_cash,
            )
            all_inputs[ticker_upper] = inputs
        except Exception as e:
            all_inputs[ticker_upper] = {"ticker": ticker_upper, "_error": str(e)}
    return all_inputs


def run_reverse_dcf(inputs, n_years=3, force_terminal_capex_equals_da=True, h_ga=None, h_gn=None, h_h=None, solve_for=None, terminal_model="gordon", full_fade_convention=True):
    ke = compute_cost_of_equity(inputs.get("risk_free_rate"), inputs.get("relevered_beta"), inputs.get("equity_risk_premium"))
    revenue = inputs.get("revenue", {})
    net_income = inputs.get("net_income", {})
    keys = ["NFY", "NFY+1", "NFY+2"][:n_years]
    fcfe_schedule = build_fcfe_schedule(
        revenue_prior=revenue.get("TTM"),
        revenue_explicit=[revenue.get(k) for k in keys],
        net_income_explicit=[net_income.get(k) for k in keys],
        depr_pct=inputs.get("depr_pct"),
        capex_pct=inputs.get("capex_pct"),
        nwc_pct=inputs.get("nwc_pct"),
        force_terminal_capex_equals_da=force_terminal_capex_equals_da,
    )
    a = compute_reconciliation_a(inputs.get("market_cap"), fcfe_schedule, ke)
    fcfe_n = fcfe_schedule[-1]["fcfe"] if fcfe_schedule else None
    result = {"ticker": inputs.get("ticker"), "ke": ke, "fcfe_schedule": fcfe_schedule, "a": a, "fcfe_n": fcfe_n}
    if terminal_model == "gordon":
        result["gordon"] = solve_gordon_growth_ltgr(a, ke, fcfe_n)
    else:
        result["h_model"] = solve_h_model(a, ke, fcfe_n, ga=h_ga, gn=h_gn, h=h_h, solve_for=solve_for, full_fade_convention=full_fade_convention)
    return result