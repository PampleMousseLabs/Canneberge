"""
web/lib/wacc_data.py

Headless WACC resolver. Any page can call get_wacc_results() and get the
same numbers the WACC page shows, whether or not /wacc has been visited.

State parsing lives here (not on the page) so DCF never imports a page.
"""

from typing import Dict, List, Optional

from Canneberge.Calculations.wacc import (
    BETA_TYPE_OPTIONS, BETA_FREQUENCY_OPTIONS, CAPITAL_STRUCTURE_OPTIONS,
    CORPORATE_RATE_SERIES,
    comp_table, column_statistics,
    risk_free_rate, pretax_cost_of_debt,
    cost_of_equity, after_tax_cost_of_debt, wacc_summary,
    parse_pct_input, to_float,
)
from web.lib.session_io import dict_to_project_inputs


def wacc_state_from_session(session_data: dict) -> dict:
    raw = (session_data or {}).get("wacc_page_state", {}) or {}

    def _opt(key, options, default):
        val = raw.get(key)
        return val if val in options else default

    return {
        "beta_type": _opt("beta_type", BETA_TYPE_OPTIONS, BETA_TYPE_OPTIONS[0]),
        "beta_frequency": _opt(
            "beta_frequency", BETA_FREQUENCY_OPTIONS, BETA_FREQUENCY_OPTIONS[0]
        ),
        "capital_structure": _opt(
            "capital_structure", CAPITAL_STRUCTURE_OPTIONS, CAPITAL_STRUCTURE_OPTIONS[0]
        ),
        "selected_debt_tic": raw.get("selected_debt_tic", ""),
        "selected_relevered_beta": raw.get("selected_relevered_beta", ""),
        "equity_risk_premium": raw.get("equity_risk_premium", ""),
        "size_premium": raw.get("size_premium", ""),
        "csrp": raw.get("csrp", ""),
        "pretax_debt_series": _opt(
            "pretax_debt_series", list(CORPORATE_RATE_SERIES.keys()),
            list(CORPORATE_RATE_SERIES.keys())[0],
        ),
        "excluded_rows": list(raw.get("excluded_rows") or []),
    }


def _exclusion_map(tickers: List[str], flags: list) -> Dict[str, bool]:
    return {
        t: (bool(flags[i]) if i < len(flags) else False)
        for i, t in enumerate(tickers)
    }


def get_wacc_results(
    session_data: dict,
    source_results: dict,
    state: Optional[dict] = None,
) -> dict:
    """Everything the WACC page renders, computed from raw session inputs."""
    state = state or wacc_state_from_session(session_data)
    inputs = dict_to_project_inputs(session_data or {})
    tickers = list(inputs.gpc_tickers or [])

    sa = (source_results or {}).get("stockanalysis", {}) or {}
    beta_vol_rows = (source_results or {}).get("beta_vol", []) or []
    fred_rows = (source_results or {}).get("fred", []) or []

    selected_debt_tic = parse_pct_input(state["selected_debt_tic"])
    selected_tax_rate = getattr(inputs, "subject_tax_rate", None)

    rows = comp_table(
        tickers=tickers,
        beta_vol_rows=beta_vol_rows,
        bs_rows=sa.get("BS", []),
        ratio_rows=sa.get("Ratios", []),
        is_rows=sa.get("IS", []),
        beta_type=state["beta_type"],
        beta_frequency=state["beta_frequency"],
        capital_structure=state["capital_structure"],
        historical_period_columns=list(inputs.historical_period_columns),
        selected_debt_tic=selected_debt_tic,
        selected_tax_rate=selected_tax_rate,
        fallback_tax_rate=selected_tax_rate,
    )
    excluded = _exclusion_map(tickers, state["excluded_rows"])
    stats = column_statistics(rows, excluded)

    rf = risk_free_rate(fred_rows)
    be = to_float(state["selected_relevered_beta"])
    erp = parse_pct_input(state["equity_risk_premium"])
    sp = parse_pct_input(state["size_premium"])
    csrp = parse_pct_input(state["csrp"])
    ke_parts = cost_of_equity(rf, be, erp, sp, csrp)

    pretax_kd = pretax_cost_of_debt(fred_rows, state["pretax_debt_series"])
    kd = after_tax_cost_of_debt(pretax_kd, selected_tax_rate)

    summary = wacc_summary(selected_debt_tic, ke_parts["cost_of_equity"], kd)

    return {
        "inputs": inputs,
        "tickers": tickers,
        "rows": rows,
        "excluded": excluded,
        "stats": stats,
        "selected_debt_tic": selected_debt_tic,
        "selected_tax_rate": selected_tax_rate,
        "rf": rf,
        "be": be,
        "adjusted_erp": ke_parts["adjusted_erp"],
        "ke": ke_parts["cost_of_equity"],
        "pretax_kd": pretax_kd,
        "after_tax_kd": kd,
        **summary,
    }


def get_discount_rate(
    session_data: dict,
    source_results: dict,
    is_fcfe: bool,
) -> Optional[float]:
    """Ke for FCFE, WACC for FCFF — same rule the desktop DCF uses."""
    calc = get_wacc_results(session_data, source_results)
    return calc["ke"] if is_fcfe else calc["wacc"]