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
) -> Dict[str, Dict[str, Optional[float]]]:
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

        # --- D&A / CapEx ---
        da = _mul(rev, projection_data.da_pct.get(period))
        capex = _mul(rev, projection_data.capex_pct.get(period))

        result[period] = {
            "revenue": rev,
            "gross_profit": gp,
            "ebitda": ebitda,
            "da": da,
            "capex": capex,
        }

    return result