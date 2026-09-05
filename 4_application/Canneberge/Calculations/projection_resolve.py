"""
Reconstructs the exact same dollar values ProjectionModulePage computes
and displays, but callable from anywhere (Subject Financials, GT, GPC)
without duplicating the dialog's math a second time from memory.

This mirrors projection_module_page.py's _recalculate/_resolve_revenue/
_resolve_gp_margin/_resolve_ebitda_margin logic exactly. If that file's
formulas ever change, this must change with it — it is not independent
logic, it is the same logic extracted.
"""

from typing import Optional, Dict, List

MS_COVERED_PERIODS = {"NFY", "NFY+1", "NFY+2"}


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _mul(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a * b


def resolve_projection_waterfall(
    adjusted_ebitda: Optional[float],
    da: Optional[float],
    other_amort: Optional[float],
    sbc: Optional[float],
    net_interest: Optional[float],
    other_adj: Optional[float],
    tax_rate: Optional[float],
    analyst_net_income: Optional[float] = None,
    solve_other_adjustment: bool = False,
) -> Dict[str, Optional[float]]:
    """Resolve the projected income-statement waterfall.

    Net interest is signed:
        positive = net interest income
        negative = net interest expense

    D&A, other amortization, and SBC are positive cost amounts.

    For public MS-covered periods, solve_other_adjustment=True makes
    Other Adjustments a pre-tax plug to analyst Net Income.
    """
    if adjusted_ebitda is None:
        ebit = None
    else:
        ebit = (
            adjusted_ebitda
            - (da or 0.0)
            - (other_amort or 0.0)
            - (sbc or 0.0)
        )

    ebt_before_adj = (
        ebit + (net_interest or 0.0)
        if ebit is not None
        else None
    )

    if solve_other_adjustment:
        resolved_other_adj = None
        if (
            ebt_before_adj is not None
            and analyst_net_income is not None
            and tax_rate is not None
            and tax_rate != 1.0
        ):
            resolved_other_adj = (
                analyst_net_income / (1.0 - tax_rate)
            ) - ebt_before_adj

        pretax_income = (
            ebt_before_adj + resolved_other_adj
            if ebt_before_adj is not None and resolved_other_adj is not None
            else None
        )
    else:
        resolved_other_adj = other_adj
        pretax_income = (
            ebt_before_adj + (resolved_other_adj or 0.0)
            if ebt_before_adj is not None
            else None
        )

    taxes = _mul(pretax_income, tax_rate)

    if solve_other_adjustment and analyst_net_income is not None:
        net_income = analyst_net_income
    elif pretax_income is not None and taxes is not None:
        net_income = pretax_income - taxes
    else:
        net_income = None

    return {
        "adjusted_ebitda": adjusted_ebitda,
        "da": da,
        "other_amort": other_amort,
        "sbc": sbc,
        "ebit": ebit,
        "net_interest": net_interest,
        "other_adj": resolved_other_adj,
        "pretax_income": pretax_income,
        "taxes": taxes,
        "net_income": net_income,
    }


def resolve_projection_dollars(
    historical_periods: List[str],
    projection_periods: List[str],
    hist_revenue: Dict[str, Optional[float]],
    hist_gross_profit: Dict[str, Optional[float]],
    hist_ebitda: Dict[str, Optional[float]],
    is_public: bool,
    ms_revenue: Dict[str, Optional[float]],
    ms_ebitda: Dict[str, Optional[float]],
    projection_data,
    ms_net_income: Optional[Dict[str, Optional[float]]] = None,
    tax_rate: Optional[float] = None,
    net_interest_by_period: Optional[Dict[str, Optional[float]]] = None,
) -> Dict[str, Dict[str, Optional[float]]]:    
    ms_net_income = ms_net_income or {}
    net_interest_by_period = net_interest_by_period or {}
    other_adj_map = getattr(projection_data, "other_adj", {}) or {}
    """
    Returns {period: {"revenue", "gross_profit", "ebitda", "da", "capex"}}
    for every period in projection_periods.

    "da" is combined Depreciation + Amortization — the dialog never
    tracks them separately, only their sum as % of Revenue.
    """
    hist_gp_margin = {
        p: _div(hist_gross_profit.get(p), hist_revenue.get(p)) for p in historical_periods
    }
    hist_ebitda_margin = {
        p: _div(hist_ebitda.get(p), hist_revenue.get(p)) for p in historical_periods
    }

    resolved_revenue: Dict[str, Optional[float]] = dict(hist_revenue)
    resolved_gp_margin: Dict[str, Optional[float]] = dict(hist_gp_margin)
    resolved_ebitda_margin: Dict[str, Optional[float]] = dict(hist_ebitda_margin)

    result: Dict[str, Dict[str, Optional[float]]] = {}

    for idx, period in enumerate(projection_periods):
        if idx == 0:
            prior_period = historical_periods[-1] if historical_periods else None
        else:
            prior_period = projection_periods[idx - 1]

        # --- Revenue ---
        if is_public and period in MS_COVERED_PERIODS:
            rev = ms_revenue.get(period)
        else:
            last = projection_data.last_edited_revenue.get(period)
            prior_rev = resolved_revenue.get(prior_period) if prior_period else None
            rev_val = projection_data.revenue.get(period)
            grow_val = projection_data.revenue_growth.get(period)

            if last == "growth" and grow_val is not None and prior_rev is not None:
                rev = prior_rev * (1.0 + grow_val)
            elif rev_val is not None:
                rev = rev_val
            elif grow_val is not None and prior_rev is not None:
                rev = prior_rev * (1.0 + grow_val)
            else:
                rev = None
        resolved_revenue[period] = rev

        # --- Gross Profit ---
        prior_gp_margin = resolved_gp_margin.get(prior_period) if prior_period else None
        gp_imp = projection_data.gp_improvement.get(period)
        if prior_gp_margin is None and gp_imp is None:
            gp_margin = None
        else:
            gp_margin = (prior_gp_margin or 0.0) + (gp_imp or 0.0)
        resolved_gp_margin[period] = gp_margin
        gp = _mul(rev, gp_margin)

        # --- EBITDA ---
        prior_ebitda_margin = resolved_ebitda_margin.get(prior_period) if prior_period else None
        if is_public and period in MS_COVERED_PERIODS:
            ebitda = ms_ebitda.get(period)
            ebitda_margin = _div(ebitda, rev)
        else:
            ebitda_imp = projection_data.ebitda_improvement.get(period)
            if prior_ebitda_margin is None and ebitda_imp is None:
                ebitda_margin = None
            else:
                ebitda_margin = (prior_ebitda_margin or 0.0) + (ebitda_imp or 0.0)
            ebitda = _mul(rev, ebitda_margin)
        resolved_ebitda_margin[period] = ebitda_margin

        # --- D&A / Other Amortization / SBC / CapEx ---
        da = _mul(rev, projection_data.da_pct.get(period))
        other_amort = _mul(
            rev, projection_data.other_amort_pct.get(period)
        )
        sbc = _mul(rev, projection_data.sbc_pct.get(period))
        capex = _mul(rev, projection_data.capex_pct.get(period))

        is_ms_period = is_public and period in MS_COVERED_PERIODS

        waterfall = resolve_projection_waterfall(
            adjusted_ebitda=ebitda,
            da=da,
            other_amort=other_amort,
            sbc=sbc,
            net_interest=net_interest_by_period.get(period),
            other_adj=other_adj_map.get(period),
            tax_rate=tax_rate,
            analyst_net_income=(
                ms_net_income.get(period) if is_ms_period else None
            ),
            solve_other_adjustment=is_ms_period,
        )

        result[period] = {
            "revenue": rev,
            "gross_profit": gp,
            "ebitda": ebitda,
            "da": da,
            "other_amort": other_amort,
            "sbc": sbc,
            "capex": capex,
            "ebit": waterfall["ebit"],
            "net_interest": waterfall["net_interest"],
            "other_adj": waterfall["other_adj"],
            "pretax_income": waterfall["pretax_income"],
            "taxes": waterfall["taxes"],
            "net_income": waterfall["net_income"],
        }

    return result