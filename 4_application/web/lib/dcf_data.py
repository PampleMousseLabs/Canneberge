"""
web/lib/dcf_data.py

Headless DCF resolver.

Dashboard and other pages must NOT import web.pages.dcf inside callbacks,
because importing a Dash page reruns dash.register_page() and crashes.

This mirrors the page's DCF state parsing and compute logic without
registering a page.
"""

from __future__ import annotations

from typing import Dict, Optional

from Canneberge.Calculations.dcf import (
    TV_MODELS,
    parse_pct,
    parse_number,
    normalise_rate,
    dcf_period_columns,
    dcf_fye_years,
    calculate_ppa,
    build_dcf,
)
from web.lib.session_io import dict_to_project_inputs
from web.lib.subject_metrics import get_subject_metric_value
from web.lib.wacc_data import get_wacc_results
from web.lib.nwc_data import get_nwc_results


_TV_DEFAULTS = {
    "Gordon Growth": {},
    "EBITDA Multiple": {"multiple": "10.00x"},
    "Revenue Multiple": {"multiple": "10.00x"},
    "H-Model": {"num_years": "5", "short_term_growth": "20.0%"},
}


def dcf_state_from_session(session_data: dict) -> dict:
    raw = (session_data or {}).get("dcf_page_state", {}) or {}
    saved_tv = raw.get("tv_inputs") or {}

    tv_inputs = {}
    for model, defaults in _TV_DEFAULTS.items():
        saved = saved_tv.get(model) or {}
        tv_inputs[model] = {
            k: (saved.get(k) if saved.get(k) is not None else d)
            for k, d in defaults.items()
        }

    model = raw.get("tv_model")
    if model not in TV_MODELS:
        model = "Gordon Growth"

    cf = raw.get("cash_flows_to")
    if cf not in ("FCFF", "FCFE"):
        cf = "FCFF"

    return {
        "ltg_input": raw.get("ltg_input", "3.0%"),
        "tv_model": model,
        "capex_dep_pct": raw.get("capex_dep_pct", "100.0%"),
        "cash_flows_to": cf,
        "other_adj_inputs": dict(raw.get("other_adj_inputs") or {}),
        "residual_amortization": raw.get("residual_amortization", ""),
        "bridge_other_adj": raw.get("bridge_other_adj", ""),
        "tv_inputs": tv_inputs,
        "sens_wacc": dict(raw.get("sens_wacc") or {}),
        "sens_ltgr": dict(raw.get("sens_ltgr") or {}),
        "nols": raw.get("nols", "No"),
        "nwc_by_mgmt": raw.get("nwc_by_mgmt", "No"),
        "valuation_approach": raw.get("valuation_approach", "DCF"),
    }


def effective_cash_flows_to(session_data: dict, state: dict) -> str:
    """Home Basis of Value overrides DCF's local toggle, matching desktop."""
    basis = (session_data or {}).get("basis_of_value")
    if basis == "Equity Value":
        return "FCFE"
    if basis == "Business Enterprise Value":
        return "FCFF"
    return state["cash_flows_to"]


def get_dcf_results(
    session_data: dict,
    source_results: dict,
    state: Optional[dict] = None,
) -> dict:
    session_data = session_data or {}
    source_results = source_results or {}
    state = state or dcf_state_from_session(session_data)

    inputs = dict_to_project_inputs(session_data)
    hist_cols = list(inputs.historical_period_columns)
    proj_cols = list(inputs.projection_period_columns)

    cash_flows_to = effective_cash_flows_to(session_data, state)
    is_fcfe = cash_flows_to == "FCFE"

    wacc_calc = get_wacc_results(session_data, source_results)
    discount_rate = wacc_calc["ke"] if is_fcfe else wacc_calc["wacc"]

    nwc_calc = get_nwc_results(session_data, source_results)
    changes = nwc_calc.get("changes", {}) or {}

    debt_state = session_data.get("debt_page_state", {}) or {}
    interest_map = debt_state.get("interest_expense_by_period") or {}
    if not interest_map:
        interest_map = debt_state.get("projected_interest") or {}

    headers, _is_hist = dcf_period_columns(hist_cols, proj_cols)

    net_interest: Dict[str, Optional[float]] = {}
    for p in headers:
        if p in hist_cols:
            inc = get_subject_metric_value(
                session_data, source_results, "interest_income", p
            )
            exp = get_subject_metric_value(
                session_data, source_results, "interest_expense", p
            )
            if inc is None and exp is None:
                net_interest[p] = None
            else:
                net_interest[p] = (inc or 0.0) - abs(exp or 0.0)
        else:
            v = parse_number(interest_map.get(p))
            net_interest[p] = -abs(v) if v is not None else None

    def sf(key: str, period: str) -> Optional[float]:
        return get_subject_metric_value(
            session_data,
            source_results,
            key,
            period,
        )

    calc = build_dcf(
        historical_period_columns=hist_cols,
        projection_period_columns=proj_cols,
        sf=sf,
        changes_in_nwc=changes,
        net_interest_by_period=net_interest,
        other_adj_inputs=state["other_adj_inputs"],
        residual_amortization=state["residual_amortization"],
        tax_rate=normalise_rate(getattr(inputs, "subject_tax_rate", None)),
        discount_rate=discount_rate,
        ltgr=parse_pct(state["ltg_input"]),
        dep_pct_of_capex=parse_pct(state["capex_dep_pct"]),
        ppa=calculate_ppa(inputs.next_fiscal_year, inputs.valuation_date),
        is_fcfe=is_fcfe,
        tv_model=state["tv_model"],
        tv_inputs=state["tv_inputs"],
        bridge_other_adj=state["bridge_other_adj"],
    )

    calc["inputs"] = inputs
    calc["cash_flows_to"] = cash_flows_to
    calc["tv_model"] = state["tv_model"]
    calc["tv_inputs"] = state["tv_inputs"]
    calc["fye"] = dcf_fye_years(
        hist_cols,
        proj_cols,
        inputs.last_fiscal_year_year,
        inputs.next_fiscal_year_year,
        inputs.nfy_1_year,
        inputs.nfy_2_year,
    )

    return calc